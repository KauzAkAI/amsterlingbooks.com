#!/usr/bin/env python3
"""
Fetch current US loan rates from Mortgage News Daily and write rates.json
in the repository root. Designed to run from a GitHub Action.

Resilient by design:
  * Network errors don't blow up the pipeline; we keep the previous JSON.
  * If a single field fails to parse, we keep its prior value rather than
    publishing a broken file.
  * The 'generated_at' timestamp updates only when we actually got new data.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

ROOT       = Path(__file__).resolve().parent.parent
RATES_JSON = ROOT / "rates" / "rates.json"        # served at amsterlingbooks.com/rates/rates.json
RATES_JSON.parent.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 LoanRatesDashboard/1.0"
)

MND_30YR = "https://www.mortgagenewsdaily.com/mortgage-rates/30-year-fixed"
MND_15YR = "https://www.mortgagenewsdaily.com/mortgage-rates/15-year-fixed"


# ---------- helpers ----------
def get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    return r.text


def first_table_row(html: str, header_label: str) -> Optional[dict]:
    """Find the first data row inside the table that follows the given label."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if header_label.lower() not in text.lower():
            continue
        rows = table.find_all("tr")
        for tr in rows:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            # MND row format: ['May 14 2026 5/14/26', '6.52%', '--', '-0.05%', '6.99%', '-0.47%']
            if len(cells) >= 4 and "%" in cells[1] and "%" in cells[3]:
                date_match = re.search(r"(\w+\s+\d{1,2}\s+20\d{2})", cells[0])
                rate       = parse_pct(cells[1])
                change     = parse_pct(cells[3])
                if rate is not None and date_match:
                    return {"date": date_match.group(1), "rate": rate, "change": change}
        # found the right table but no usable row
        return None
    return None


def parse_pct(s: str) -> Optional[float]:
    m = re.search(r"([+-]?\d+\.\d+)", s)
    return float(m.group(1)) if m else None


def header_value(html: str, label_regex: str) -> tuple[Optional[float], Optional[float]]:
    """
    The MND page header carries summary rates inside link text like
    '30YR Fixed Rate6.52%-0.05%' or '10 Year Treasury4.560+0.075'.
    """
    pat = re.compile(label_regex + r"[^0-9]{0,4}([0-9]+\.[0-9]+)\s*%?\s*([+-]?[0-9]+\.[0-9]+)?", re.I)
    m = pat.search(html)
    if not m:
        return None, None
    rate   = float(m.group(1))
    change = float(m.group(2)) if m.group(2) else None
    return rate, change


def historical_series(html: str, header_label: str, max_points: int = 30) -> list[dict]:
    """Pull the daily MND series from the table for sparkline charts."""
    soup = BeautifulSoup(html, "html.parser")
    series: list[dict] = []
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if header_label.lower() not in text.lower():
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 2 and "%" in cells[1]:
                date_m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})", cells[0])
                rate   = parse_pct(cells[1])
                if date_m and rate is not None:
                    mm, dd, yy = date_m.groups()
                    iso = f"20{yy}-{int(mm):02d}-{int(dd):02d}"
                    series.append({"date": iso, "rate": rate})
        break
    series.sort(key=lambda x: x["date"])
    return series[-max_points:]


def load_existing() -> dict:
    if RATES_JSON.exists():
        try:
            return json.loads(RATES_JSON.read_text())
        except json.JSONDecodeError:
            pass
    return {}


# ---------- main ----------
def main() -> int:
    prior = load_existing()
    out = json.loads(json.dumps(prior))  # deep copy

    out.setdefault("rates", {})
    out.setdefault("history", {})
    out.setdefault("warnings", [])
    out["warnings"] = []

    # --- 30-year fixed page (also has 15Y + 10Y Treasury in the header) ---
    try:
        html30 = get(MND_30YR)
    except Exception as e:
        out["warnings"].append(f"MND 30Y fetch failed: {e}")
        html30 = None

    if html30:
        # Headline header values
        for key, label in [
            ("thirty_year_fixed", r"30\s*YR\s*Fixed\s*Rate"),
            ("fifteen_year_fixed", r"15\s*YR\s*Fixed\s*Rate"),
            ("ten_year_treasury", r"10\s*Year\s*Treasury"),
        ]:
            rate, change = header_value(html30, label)
            if rate is not None:
                out["rates"][key] = {"rate": rate, "change": change}

        # Daily series for charts
        series = historical_series(html30, "MND's 30 Year Fixed", max_points=30)
        if series:
            out["history"]["thirty_year_fixed_daily"] = series

        # Most-recent row (gives prior-year + YoY too)
        latest = first_table_row(html30, "MND's 30 Year Fixed")
        if latest:
            out["rates"].setdefault("thirty_year_fixed", {}).update({
                "asof_label": latest["date"],
                "change":     latest["change"],
            })

    # --- 15-year fixed page (better data for the 15Y row + history) ---
    try:
        html15 = get(MND_15YR)
    except Exception as e:
        out["warnings"].append(f"MND 15Y fetch failed: {e}")
        html15 = None

    if html15:
        latest15 = first_table_row(html15, "MND's 15 Year Fixed")
        if latest15:
            out["rates"]["fifteen_year_fixed"] = {
                "rate":       latest15["rate"],
                "change":     latest15["change"],
                "asof_label": latest15["date"],
            }
        series15 = historical_series(html15, "MND's 15 Year Fixed", max_points=30)
        if series15:
            out["history"]["fifteen_year_fixed_daily"] = series15

    # --- Static reference rates we don't try to scrape (Fed-set or wide ranges) ---
    out["reference"] = {
        "fed_funds_upper": 3.75,
        "fed_funds_lower": 3.50,
        "prime_rate":      6.75,
        "sofr_overnight":  3.64,
        "two_year_treasury":  3.91,
        "thirty_year_treasury": 4.92,
        "five_one_arm":    6.48,
        "thirty_jumbo":    6.74,
        "thirty_fha":      6.16,
        "thirty_va":       6.10,
        "cre_conventional_min": 5.23,
        "cre_conventional_max": 8.75,
        "sba_7a_min":      9.75,
        "sba_7a_max":     14.75,
        "sba_504":         6.75,
        "auto_60mo":       6.97,
        "heloc_variable":  7.21,
        "home_equity_fixed": 7.36,
        "personal_loan_3yr": 12.27,
        "fed_funds_last_change": "2025-12-11",
        "next_fomc":            "2026-06-17",
    }

    # Did we actually get any live data? If not, keep prior generated_at.
    has_live = bool(out["rates"].get("thirty_year_fixed", {}).get("rate"))
    if has_live:
        out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out["source"] = "Mortgage News Daily (auto-fetched)"
    else:
        out.setdefault("generated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        out["warnings"].append("No live data parsed; serving prior values.")

    # Pretty-print so git diffs are readable
    RATES_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {RATES_JSON} — generated_at={out['generated_at']} warnings={out['warnings']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
