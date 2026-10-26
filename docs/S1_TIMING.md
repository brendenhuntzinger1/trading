# S1: what "morning momentum" means and when it trades

**The label.** The pre-registered name is *market intraday momentum*. I called it "morning momentum" in a status
message, as shorthand for where its **signal** comes from: the overnight move plus the first trading hour. The
**trade** happens at the end of the day. Those are different times, and the shorthand blurred them.

| Item | Definition |
|---|---|
| Timezone | America/New_York (exchange time). Stored internally in UTC. |
| Daylight saving | Session times come from `exchange_calendars` (XNYS). The 09:30 ET open is 13:30 UTC under EDT and 14:30 UTC under EST, so no fixed UTC offset is ever used. Yahoo timestamps are UTC epochs, converted with the same tz database. |
| Signal observation window | From the **previous session's official close** (16:00 ET; 13:00 ET on half-days) to **10:30 ET**: the close of the 09:30–10:30 hourly bar. This includes the overnight gap. |
| Signal | r = price at 10:30 / previous official close − 1. Long when r ≥ +0.25%; top 5 by r. |
| Decision time | 15:30 ET, the end of the 14:30–15:30 bar. Bars are used only after they end. |
| Entry (research and engine) | The first trade of the 15:30–16:00 hourly bar (the bar's open), plus the assumed 5 bp cost. **Live equivalent:** a marketable order sent at 15:30:00 ET, filled seconds later at the prevailing ask. The hourly data can't verify that price. |
| Exit | Official closing price (closing auction, MOC). The engine replay uses the last hourly bar's close; the median difference from the official close is 1.5 bp. **Live equivalent:** an MOC order submitted before the NYSE 15:50 ET MOC cutoff. |
| Maximum holding | 30 minutes (15:30 → 16:00). |
| Half-days | Skipped. There is no 15:30 bar when the market closes at 13:00. The engine matches the research (1,445 / 1,445 trades). |
| Data-validity filter | Skip a symbol-session if the hourly 09:30 open differs from the official open by > 2% (caught the BNY ticker reuse). |

**Why 10:30, not 10:00 as in the source paper.** Gao et al. (2018) use the first half hour. Yahoo hourly bars
start at 09:30, so the earliest observable checkpoint is 10:30. This was pre-registered as such; it is a
deviation from the paper, imposed by the data.
