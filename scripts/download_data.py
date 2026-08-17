"""Download the raw 1-minute SPY dataset into data/raw/.

Source: public GitHub repository `prsdro/spy` (data/candles_1m.csv.gz),
1-minute OHLCV bars 2000-01 .. 2026-04, bar-start timestamps, US/Eastern,
including extended hours.  Validated in research against official closing
prints (see docs/01_RESEARCH_REPORT.md, Q1/data section).
"""
from __future__ import annotations

import os
import urllib.request

URL = "https://api.github.com/repos/prsdro/spy/contents/data/candles_1m.csv.gz"
DEST = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "candles_1m.csv.gz")


def main():
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    req = urllib.request.Request(URL, headers={
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "sphinx-research",
    })
    print(f"downloading {URL} ...")
    with urllib.request.urlopen(req) as r, open(DEST, "wb") as f:
        f.write(r.read())
    print(f"saved {DEST} ({os.path.getsize(DEST)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
