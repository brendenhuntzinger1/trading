"""Deterministic keyword classifier: the default, and the fallback when the
optional LLM classifier is off or its output is rejected. Every assignment
carries the verbatim sentence that triggered it."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import Category

ASSET_PATTERNS = {
    "BTC": r"\b(bitcoin|btc)\b",
    "ETH": r"\b(ethereum|ether|eth)\b",
    "SOL": r"\b(solana|(?-i:SOL))\b",
    "LTC": r"\b(litecoin|ltc)\b",
    "BCH": r"\b(bitcoin cash|bch)\b",
    "ETC": r"\b(ethereum classic|(?-i:ETC))\b",   # bare lower-case "etc." is an abbreviation
    "crypto_market": r"\b(crypto(currenc(y|ies))?|digital assets?|stablecoins?|virtual currenc(y|ies)|tokens?)\b",
    "USD": r"\b(dollar|treasur(y|ies)|federal funds|fed funds)\b",
}
# Order matters: first match wins.
MECHANISM_RULES = [
    ("venue_operational", r"\b(outage|degraded|halt(ed)?|suspend(ed)?|maintenance|withdrawals? (delayed|paused|disabled)|deposits? (delayed|paused|disabled)|incident)\b"),
    ("enforcement_flows", r"\b(seiz(e|ed|ure)|charg(e|ed|es)|fraud|indict(ed|ment)|settle(d|ment)|penalt(y|ies)|enforcement)\b"),
    ("regulatory_access", r"\b(approv(e|ed|al)|ban(ned|s)?|rule(making)?|regulat(ion|ory)|licen[cs]e|framework|etf|guidance)\b"),
    ("inflation_surprise", r"\b(consumer price index|cpi|inflation|pce price)\b"),
    ("labor_surprise", r"\b(payrolls?|unemployment|employment situation|jobless)\b"),
    ("growth_surprise", r"\b(gross domestic product|gdp|personal income)\b"),
    ("rates_liquidity", r"\b(federal open market committee|fomc|federal funds rate|monetary policy|interest rates?|balance sheet)\b"),
    ("geopolitical_risk_off", r"\b(war|missile|invasion|sanction(s|ed)?|military|strike|conflict|blockade|tariffs?)\b"),
    ("capital_controls_demand", r"\b(capital controls?|devaluation|currency crisis|hyperinflation)\b"),
    ("asset_specific_supply", r"\b(hack(ed)?|exploit(ed)?|unlock|upgrade|hard fork|halving|inflows?|outflows?)\b"),
]
CATEGORY_RULES = [
    (Category.EXCHANGE_INCIDENT, r"\b(outage|degraded|maintenance|withdrawals? (delayed|paused)|deposits? (delayed|paused))\b"),
    (Category.CENTRAL_BANK, r"\b(federal reserve|fomc|federal open market committee|monetary policy|central bank)\b"),
    (Category.MACRO_RELEASE, r"\b(consumer price index|cpi|payrolls|gdp|gross domestic product|personal income)\b"),
    (Category.REGULATORY, r"\b((?-i:SEC)|cftc|securities and exchange commission|regulat(or|ion|ory)|enforcement|charges)\b"),
    (Category.GEOPOLITICAL, r"\b(war|sanction|military|missile|conflict|invasion|tariff)\b"),
]


@dataclass
class Classification:
    category: Category
    assets: list[str]
    mechanism: str
    evidence: list[str] = field(default_factory=list)
    classifier: str = "keyword"


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def classify(title: str, body: str = "", default: Category = Category.OTHER) -> Classification:
    text = f"{title}. {body}"
    sents = sentences(text)
    evidence: list[str] = []

    def find(pattern: str) -> str | None:
        for s in sents:
            if re.search(pattern, s, re.I):
                return s
        return None

    assets = []
    for a, pat in ASSET_PATTERNS.items():
        s = find(pat)
        if s:
            assets.append(a)
            evidence.append(s)
    mechanism = "unclear"
    for m, pat in MECHANISM_RULES:
        s = find(pat)
        if s:
            mechanism = m
            evidence.append(s)
            break
    category = default
    if default is Category.OTHER:
        for c, pat in CATEGORY_RULES:
            if find(pat):
                category = c
                break
        else:
            if assets and set(assets) != {"USD"}:
                category = Category.ASSET_NEWS
    return Classification(category, assets, mechanism, list(dict.fromkeys(evidence)))
