"""Scheduled macro calendar (FOMC decisions, CPI and payrolls releases), built
only from official pages. Every row cites the page its date and time came from.

Point-in-time note: scheduled FOMC meetings and BLS release dates are published
well in advance, so they are legitimate backtest inputs. Unscheduled FOMC
actions are NOT known in advance (known_in_advance=False) and must not be used
as pre-scheduled flags. Rows use the ACTUAL release date; a release that was
rescheduled after its date was announced would leak slightly - `irregular`
marks dates outside the usual pattern for review."""
from __future__ import annotations

import csv
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .sources import USER_AGENT, fetch

ET_TZ = ZoneInfo("America/New_York")
CAL_PATH = Path(__file__).resolve().parents[2] / "data" / "events" / "macro_calendar.csv"
FED = "https://www.federalreserve.gov"
FOMC_CURRENT = f"{FED}/monetarypolicy/fomccalendars.htm"
FOMC_HISTORICAL = f"{FED}/monetarypolicy/fomchistorical{{y}}.htm"
BLS = "https://www.bls.gov"
BLS_ARCHIVE = {"cpi": f"{BLS}/bls/news-release/cpi.htm", "empsit": f"{BLS}/bls/news-release/empsit.htm"}
BLS_SCHEDULE = {"cpi": f"{BLS}/schedule/news_release/cpi.htm", "empsit": f"{BLS}/schedule/news_release/empsit.htm"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
ABBR = {m[:3]: i for m, i in MONTHS.items()}


@dataclass
class CalendarRow:
    kind: str                # fomc_decision | fomc_unscheduled | fomc_notation_vote | fomc_cancelled | cpi_release | nfp_release
    reference: str           # meeting label or reference month
    release_utc: str         # ISO UTC; empty if unknown
    release_local: str       # as printed by the source, e.g. "2:00 p.m. EST"
    known_in_advance: bool
    irregular: bool
    source_url: str          # page the time came from
    index_url: str           # page the date/listing came from
    note: str = ""


CACHE = CAL_PATH.parent / "cache"


def _head(url: str, limit: int = 200_000) -> str | None:
    """First `limit` bytes of an official page (cached on disk). None if unavailable."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[1])
    if f.exists():
        return f.read_text()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read(limit).decode("utf-8", "ignore")
    except urllib.error.HTTPError as ex:
        return None if ex.code in (404, 410) else _raise(ex)
    f.write_text(text)
    time.sleep(0.4)
    return text


def _raise(ex):
    raise ex


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _local_to_utc(d: date, hhmm: str, ampm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    h = h % 12 + (12 if ampm.lower().startswith("p") else 0)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=ET_TZ).astimezone(timezone.utc)


# ---- FOMC ----------------------------------------------------------------------
def _fomc_meetings() -> list[tuple[str, str, str]]:
    """(label, statement_code or '', index_url) for 2018 onward."""
    out = []
    for y in (2018, 2019, 2020):
        url = FOMC_HISTORICAL.format(y=y)
        html = fetch(url).decode("utf-8", "ignore")
        parts = re.split(r"<h5[^>]*>", html)[1:]
        for p in parts:
            label = _strip(p.split("</h5>")[0])
            code = re.search(r"pressreleases/(monetary\d{8}a)\.htm", p)
            out.append((label, code.group(1) if code else "", url))
    html = fetch(FOMC_CURRENT).decode("utf-8", "ignore")
    for panel in re.split(r'<div class="panel panel-default">', html)[1:]:
        ym = re.search(r"(\d{4}) FOMC Meetings", panel)
        if not ym:
            continue
        for row in re.split(r'class="[^"]*row fomc-meeting"', panel)[1:]:
            month = re.search(r"fomc-meeting__month[^>]*><strong>([^<]+)", row)
            day = re.search(r"fomc-meeting__date[^>]*>([^<]+)", row)
            if not (month and day):
                continue
            code = re.search(r"pressreleases/(monetary\d{8}a)\.htm", row)
            out.append((f"{month.group(1).strip()} {day.group(1).strip()} - {ym.group(1)}",
                        code.group(1) if code else "", FOMC_CURRENT))
    return out


ASSUMED_FOMC_TIME = ("2:00", "p")


def meeting_end(label: str) -> date | None:
    """'October 27-28 - 2026', 'Apr/May 30-1 - 2027', 'December 8-9* - 2026' -> last meeting day."""
    m = re.match(r"([A-Za-z/]+)\s+(\d{1,2})(?:-(\d{1,2}))?\*?.*?(\d{4})", label)
    if not m:
        return None
    months = m.group(1).lower().split("/")
    month = MONTHS.get(months[-1]) or ABBR.get(months[-1][:3])
    return date(int(m.group(4)), month, int(m.group(3) or m.group(2))) if month else None


def fomc_rows() -> list[CalendarRow]:
    rows = []
    for label, code, index_url in _fomc_meetings():
        low = label.lower()
        kind = ("fomc_cancelled" if "cancel" in low else "fomc_notation_vote" if "notation" in low
                else "fomc_unscheduled" if "unscheduled" in low else "fomc_decision")
        if not code:   # future meeting (no statement yet) or cancelled
            d = meeting_end(label) if kind == "fomc_decision" else None
            utc = _local_to_utc(d, *ASSUMED_FOMC_TIME).isoformat() if d else ""
            rows.append(CalendarRow(kind, label, utc, "2:00 p.m. ET (assumed)" if d else "", kind != "fomc_unscheduled",
                                    False, "", index_url,
                                    "date from official calendar; time assumed = the 2:00 p.m. ET printed on every "
                                    "2018-2026 scheduled statement; confirm when the statement is published" if d else ""))
            continue
        url = f"{FED}/newsevents/pressreleases/{code}.htm"
        page = _head(url, 400_000)
        m = re.search(r"For release at\s+(\d{1,2}:\d{2})\s*([ap])\.m\.\s*(E[SD]T)", page or "", re.I)
        d = datetime.strptime(code[8:16], "%Y%m%d").date()
        utc = _local_to_utc(d, m.group(1), m.group(2)).isoformat() if m else ""
        rows.append(CalendarRow(kind, label, utc, f"{m.group(1)} {m.group(2)}.m. {m.group(3)}" if m else "",
                                kind == "fomc_decision", False, url, index_url,
                                "" if m else "statement page unavailable" if page is None
                                else "release time not found on statement page"))
    return rows


# ---- BLS releases ----------------------------------------------------------------
EMBARGO = re.compile(r"embargoed until\s+(?:USDL-[\d-]+\s+)?(\d{1,2}:\d{2})\s*([ap])\.m\.\s*\((E[SD]?T)\)", re.I)


def bls_rows(series: str, since_year: int = 2018) -> list[CalendarRow]:
    kind = {"cpi": "cpi_release", "empsit": "nfp_release"}[series]
    html = fetch(BLS_ARCHIVE[series]).decode("utf-8", "ignore")
    found = re.findall(rf'href="(?:https?://www\.bls\.gov)?(/news\.release/archives/{series}_(\d{{8}})\.htm)"[^>]*>([^<]+)</a>', html)
    rows, seen = [], set()
    for path, mmddyyyy, label in found:
        d = datetime.strptime(mmddyyyy, "%m%d%Y").date()
        if d.year < since_year or path in seen or d > date.today():   # future: taken from the schedule page
            continue
        seen.add(path)
        url = BLS + path
        page = _head(url)
        m = EMBARGO.search(_strip(page)) if page else None
        utc = _local_to_utc(d, m.group(1), m.group(2)).isoformat() if m else ""
        # CPI is normally released on business days 10-15 and payrolls on days 1-10 of the month
        lo, hi = (9, 16) if series == "cpi" else (1, 10)
        rows.append(CalendarRow(kind, _strip(label), utc, f"{m.group(1)} {m.group(2)}.m. {m.group(3)}" if m else "",
                                True, not (lo <= d.day <= hi), url, BLS_ARCHIVE[series],
                                "" if m else "release page unavailable (HTTP 404); time unknown" if page is None
                                else "embargo time not found on release page"))
    # Announced future releases (schedule page), not yet in the archive.
    sched = fetch(BLS_SCHEDULE[series]).decode("utf-8", "ignore")
    for ref, day, tm in re.findall(r"<td>([A-Z][a-z]+ \d{4})</td>\s*<td>([A-Z][a-z]{2,4}\.? \d{1,2}, \d{4})</td>\s*<td>(\d{2}:\d{2} [AP]M)</td>", sched):
        d = datetime.strptime(day.replace(".", "").replace("Sept", "Sep"), "%b %d, %Y").date()
        if any(r.release_utc.startswith(d.isoformat()) for r in rows) or d < date.today():
            continue
        hhmm, ampm = tm.split()
        rows.append(CalendarRow(kind, f"{ref} (scheduled)", _local_to_utc(d, hhmm, ampm).isoformat(),
                                f"{tm} ET", True, False, BLS_SCHEDULE[series], BLS_SCHEDULE[series],
                                "future release from published schedule"))
    return rows


def build(path: Path = CAL_PATH) -> list[CalendarRow]:
    rows = fomc_rows() + bls_rows("cpi") + bls_rows("empsit")
    rows.sort(key=lambda r: (r.release_utc or "9999", r.kind))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[f.name for f in fields(CalendarRow)])
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    return rows


def load(path: Path = CAL_PATH) -> list[CalendarRow]:
    with path.open() as fh:
        return [CalendarRow(**{**r, "known_in_advance": r["known_in_advance"] == "True",
                               "irregular": r["irregular"] == "True"}) for r in csv.DictReader(fh)]


def scheduled_between(rows: list[CalendarRow], start: datetime, end: datetime) -> list[CalendarRow]:
    """Releases known in advance whose time falls in [start, end]."""
    out = []
    for r in rows:
        if r.known_in_advance and r.release_utc:
            t = datetime.fromisoformat(r.release_utc)
            if start <= t <= end:
                out.append(r)
    return out
