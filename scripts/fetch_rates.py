#!/usr/bin/env python3
"""
Fetch current US loan rates, forex, indices, commodities, treasury curve, and
news for the amsterlingbooks.com/rates/ dashboard. Writes rates/rates.json.

Resilient by design: each section is wrapped in try/except. A failure in one
source never breaks the whole pipeline — prior values are preserved instead.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

ROOT       = Path(__file__).resolve().parent.parent
RATES_JSON = ROOT / "rates" / "rates.json"
RATES_JSON.parent.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 LoanRatesDashboard/2.0"
)
HDR = {"User-Agent": UA, "Accept": "text/html,application/json,*/*"}

MND_30YR = "https://www.mortgagenewsdaily.com/mortgage-rates/30-year-fixed"
MND_15YR = "https://www.mortgagenewsdaily.com/mortgage-rates/15-year-fixed"


# ---------- generic helpers ----------
def safe(label: str, fn, *args, **kwargs):
    """Run fn; on exception, append a warning and return None."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        warnings.append(f"{label} failed: {type(e).__name__}: {str(e)[:120]}")
        return None


def get(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers=HDR, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_pct(s: str) -> Optional[float]:
    m = re.search(r"([+-]?\d+\.\d+)", s)
    return float(m.group(1)) if m else None


# ---------- MND scrapers ----------
def first_table_row(html: str, header_label: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        if header_label.lower() not in table.get_text(" ", strip=True).lower():
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 4 and "%" in cells[1] and "%" in cells[3]:
                dm = re.search(r"(\w+\s+\d{1,2}\s+20\d{2})", cells[0])
                r = parse_pct(cells[1]); c = parse_pct(cells[3])
                if r is not None and dm:
                    return {"date": dm.group(1), "rate": r, "change": c}
        return None
    return None


def header_value(html: str, label_re: str):
    pat = re.compile(label_re + r"[^0-9]{0,4}([0-9]+\.[0-9]+)\s*%?\s*([+-]?[0-9]+\.[0-9]+)?", re.I)
    m = pat.search(html)
    if not m: return (None, None)
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def historical_series(html: str, header_label: str, max_points: int = 30) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.find_all("table"):
        if header_label.lower() not in table.get_text(" ", strip=True).lower():
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 2 and "%" in cells[1]:
                dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})", cells[0])
                r = parse_pct(cells[1])
                if dm and r is not None:
                    mm, dd, yy = dm.groups()
                    out.append({"date": f"20{yy}-{int(mm):02d}-{int(dd):02d}", "rate": r})
        break
    out.sort(key=lambda x: x["date"])
    return out[-max_points:]


def fetch_mnd(out: dict):
    html30 = get(MND_30YR)
    for key, lbl in [
        ("thirty_year_fixed", r"30\s*YR\s*Fixed\s*Rate"),
        ("fifteen_year_fixed", r"15\s*YR\s*Fixed\s*Rate"),
        ("ten_year_treasury", r"10\s*Year\s*Treasury"),
    ]:
        r, c = header_value(html30, lbl)
        if r is not None:
            out["rates"][key] = {"rate": r, "change": c}
    series = historical_series(html30, "MND's 30 Year Fixed", 30)
    if series:
        out["history"]["thirty_year_fixed_daily"] = series
    latest = first_table_row(html30, "MND's 30 Year Fixed")
    if latest:
        out["rates"].setdefault("thirty_year_fixed", {}).update({
            "asof_label": latest["date"], "change": latest["change"]
        })
    html15 = get(MND_15YR)
    l15 = first_table_row(html15, "MND's 15 Year Fixed")
    if l15:
        out["rates"]["fifteen_year_fixed"] = {
            "rate": l15["rate"], "change": l15["change"], "asof_label": l15["date"]
        }


# ---------- forex via frankfurter.app (ECB rates, free, no key) ----------
def fetch_forex(out: dict):
    targets = ["EUR", "GBP", "JPY", "CNY", "KRW", "INR", "CAD", "MXN"]
    meta = {
        "EUR": ("Euro", "🇪🇺"), "GBP": ("British Pound", "🇬🇧"),
        "JPY": ("Japanese Yen", "🇯🇵"), "CNY": ("Chinese Yuan", "🇨🇳"),
        "KRW": ("Korean Won", "🇰🇷"), "INR": ("Indian Rupee", "🇮🇳"),
        "CAD": ("Canadian Dollar", "🇨🇦"), "MXN": ("Mexican Peso", "🇲🇽"),
    }
    today_url = "https://api.frankfurter.app/latest?from=USD&to=" + ",".join(targets)
    today = requests.get(today_url, timeout=20).json()
    rates = today.get("rates", {})
    yest_url = "https://api.frankfurter.app/P5D?from=USD&to=" + ",".join(targets)
    hist = requests.get(yest_url, timeout=20).json()
    hist_rates = hist.get("rates", {})
    dates_sorted = sorted(hist_rates.keys()) if hist_rates else []
    prior_rates = hist_rates.get(dates_sorted[0], {}) if dates_sorted else {}

    fx = {}
    for code in targets:
        cur = rates.get(code)
        prev = prior_rates.get(code)
        if cur is None: continue
        change_pct = ((cur - prev) / prev * 100) if (prev and prev != 0) else 0
        name, flag = meta[code]
        fx[code] = {"rate": cur, "name": name, "flag": flag,
                    "change_pct": round(change_pct, 2)}
    try:
        dxy_txt = get("https://stooq.com/q/?s=^dxy&f=ohlcv&i=d&o=1111111&c=0", 15)
        dm = re.search(r"Last:\s*<[^>]+>([\d.]+)", dxy_txt)
        if dm:
            fx["DXY"] = {"rate": float(dm.group(1)), "name": "US Dollar Index",
                         "flag": "🇺🇸", "change_pct": 0}
    except Exception:
        pass
    if fx:
        out["forex"] = fx


# ---------- Treasury yield curve ----------
def fetch_treasury_curve(out: dict):
    month_token = datetime.now(timezone.utc).strftime("%Y%m")
    url = ("https://home.treasury.gov/resource-center/data-chart-center/"
           f"interest-rates/daily-treasury-rates.csv/all/{month_token}?"
           f"type=daily_treasury_yield_curve&field_tdr_date_value_month={month_token}")
    try:
        csv_text = get(url, 20)
        lines = [l for l in csv_text.splitlines() if l.strip()]
        if len(lines) >= 2:
            header = [h.strip().strip('"') for h in lines[0].split(",")]
            row = [c.strip().strip('"') for c in lines[1].split(",")]
            tenors = {
                "1 Mo": "1M", "3 Mo": "3M", "6 Mo": "6M", "1 Yr": "1Y",
                "2 Yr": "2Y", "5 Yr": "5Y", "7 Yr": "7Y", "10 Yr": "10Y",
                "20 Yr": "20Y", "30 Yr": "30Y",
            }
            curve = []
            for hdr_label, short in tenors.items():
                if hdr_label in header:
                    idx = header.index(hdr_label)
                    if idx < len(row) and row[idx]:
                        try:
                            curve.append({"tenor": short, "yield": float(row[idx])})
                        except ValueError:
                            pass
            if curve:
                out["treasury_curve"] = curve
    except Exception:
        pass


# ---------- Stock indices + commodities via stooq.com ----------
def stooq_quote(ticker: str) -> Optional[dict]:
    url = f"https://stooq.com/q/l/?s={ticker}&f=sd2t2ohlcv&h&e=csv"
    try:
        csv = get(url, 15)
        rows = [r for r in csv.splitlines() if r.strip()]
        if len(rows) < 2: return None
        hdr = rows[0].split(",")
        vals = rows[1].split(",")
        d = dict(zip([h.lower() for h in hdr], vals))
        close = float(d.get("close", "nan"))
        open_ = float(d.get("open", "nan"))
        if close != close: return None
        change = close - open_
        pct = (change / open_ * 100) if open_ else 0
        return {"value": close, "change": round(change, 2), "change_pct": round(pct, 2)}
    except Exception:
        return None


def fetch_indices(out: dict):
    mapping = {"sp500": "^spx", "nasdaq": "^ndq", "dow": "^dji", "vix": "^vix"}
    new = {}
    for key, tk in mapping.items():
        q = stooq_quote(tk)
        if q:
            new[key] = q
    if new:
        out["indices"] = {**out.get("indices", {}), **new}


def fetch_commodities(out: dict):
    mapping = {
        "wti_oil":     ("cl.f",  "$/bbl"),
        "brent_oil":   ("b.f",   "$/bbl"),
        "gold":        ("gc.f",  "$/oz"),
        "silver":      ("si.f",  "$/oz"),
        "natural_gas": ("ng.f",  "$/MMBtu"),
        "copper":      ("hg.f",  "$/lb"),
    }
    new = {}
    for key, (tk, unit) in mapping.items():
        q = stooq_quote(tk)
        if q:
            q["unit"] = unit
            new[key] = q
    if new:
        out["commodities"] = {**out.get("commodities", {}), **new}


# ---------- News headlines via RSS ----------
def fetch_news(out: dict):
    feeds = [
        ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
        ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
        ("Reuters Business", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"),
    ]
    items = []
    for source, url in feeds:
        try:
            xml = get(url, 12)
            root = ET.fromstring(xml)
            channel = root.find("channel") or root
            for it in channel.findall(".//item")[:5]:
                t = (it.findtext("title") or "").strip()
                l = (it.findtext("link") or "").strip()
                p = (it.findtext("pubDate") or "").strip()
                if t and l:
                    items.append({"title": t[:160], "url": l, "source": source, "published": p[:25]})
        except Exception:
            continue
    if items:
        out["news"] = items[:12]


# ---------- Bank rates (static reference) ----------
def ensure_bank_defaults(out: dict):
    out.setdefault("banks", {})
    defaults = {
        "chase": {
            "name": "Chase",
            "url":  "https://www.chase.com/personal/mortgage/mortgage-rates",
            "mortgage_30yr": 6.50, "mortgage_15yr": 5.75, "auto_new": 7.49,
            "cd_12mo": 2.00, "cd_special": 3.50, "savings": 0.01
        },
        "wells_fargo": {
            "name": "Wells Fargo",
            "url":  "https://www.wellsfargo.com/mortgage/rates/",
            "mortgage_30yr": 6.82, "mortgage_15yr": 5.43, "auto_new": 7.99,
            "cd_12mo": 1.50, "cd_special": 3.75, "savings": 0.01
        },
        "bank_of_america": {
            "name": "Bank of America",
            "url":  "https://www.bankofamerica.com/mortgage/",
            "mortgage_30yr": 6.63, "mortgage_15yr": 5.88, "auto_new": 7.39,
            "cd_12mo": 3.40, "cd_special": 4.00, "savings": 0.04
        },
        "capital_city_bank": {
            "name": "Capital City Bank (FL)",
            "url":  "https://www.ccbg.com/",
            "mortgage_30yr": 7.10, "mortgage_15yr": 6.20, "auto_new": 7.75,
            "cd_12mo": 3.85, "cd_special": 4.25, "savings": 0.10
        },
    }
    for k, v in defaults.items():
        if k not in out["banks"]:
            out["banks"][k] = v


# ---------- Static reference fallbacks ----------
def ensure_reference_defaults(out: dict):
    refs = out.setdefault("reference", {})
    fallback = {
        "fed_funds_upper": 3.75, "fed_funds_lower": 3.50, "prime_rate": 6.75,
        "sofr_overnight": 3.64, "two_year_treasury": 3.91, "thirty_year_treasury": 5.02,
        "five_one_arm": 6.48, "thirty_jumbo": 6.74, "thirty_fha": 6.16, "thirty_va": 6.10,
        "cre_conventional_min": 5.23, "cre_conventional_max": 8.75,
        "sba_7a_min": 9.75, "sba_7a_max": 14.75, "sba_504": 6.75,
        "auto_60mo": 6.97, "heloc_variable": 7.21, "home_equity_fixed": 7.36,
        "personal_loan_3yr": 12.27,
        "fed_funds_last_change": "2025-12-11", "next_fomc": "2026-06-17",
    }
    for k, v in fallback.items():
        refs.setdefault(k, v)


# ---------- main ----------
warnings: list[str] = []

def main() -> int:
    prior = {}
    if RATES_JSON.exists():
        try: prior = json.loads(RATES_JSON.read_text())
        except json.JSONDecodeError: pass

    out = json.loads(json.dumps(prior))
    out.setdefault("rates", {})
    out.setdefault("history", {})
    out["warnings"] = []
    globals()["warnings"] = out["warnings"]

    safe("MND",        fetch_mnd,             out)
    safe("Forex",      fetch_forex,           out)
    safe("Treasury",   fetch_treasury_curve,  out)
    safe("Indices",    fetch_indices,         out)
    safe("Commodities",fetch_commodities,     out)
    safe("News",       fetch_news,            out)

    ensure_bank_defaults(out)
    ensure_reference_defaults(out)

    if out["rates"].get("thirty_year_fixed", {}).get("rate"):
        out["source"] = "Live (MND + frankfurter + stooq + RSS)"
    else:
        out.setdefault("source", "Prior values (no live fetch succeeded)")
    out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    RATES_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {RATES_JSON} · generated_at={out['generated_at']} · warnings={out['warnings']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
