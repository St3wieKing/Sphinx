"""Data loading and session preparation.

Raw input: 1-minute OHLCV bars, bar-START timestamps in US/Eastern,
including pre/post market. Source file: data/raw/candles_1m.csv.gz.

All downstream code consumes:
  * minute_rth : 1-minute bars restricted to the regular session
  * sessions   : one row per trading day with session metadata and
                 daily reference values (prev close, ATR, vol, SMA)
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

RAW_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "candles_1m.csv.gz")
CACHE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cache.pkl")

RTH_OPEN = "09:30"
RTH_LAST_FULL = "15:59"   # last 1-min bar (bar-start label) of a full session
HALF_DAY_LAST = "12:59"   # last bar of an early-close session


def load_minute(raw_csv: str = None) -> pd.DataFrame:
    """Load, dedupe and sort the raw 1-minute file (all hours)."""
    path = raw_csv or RAW_CSV
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp")
    # keep the LAST record for duplicated timestamps (vendor corrections)
    df = df[~df["timestamp"].duplicated(keep="last")]
    df = df.set_index("timestamp")
    return df


def build_sessions(minute_all: pd.DataFrame):
    """Return (minute_rth, sessions).

    sessions columns:
      date, open_time, close_time, is_half_day, o/h/l/c (RTH), volume,
      prev_close, gap, atr14 (daily, previous 14 sessions), rv20 (ann.
      realized vol of prior 20 close-to-close returns), sma200 (of prior
      closes), n_bars
    All reference columns use STRICTLY PRIOR data (shifted), so no
    look-ahead is possible.
    """
    rth = minute_all.between_time("09:30", "15:59").copy()
    dates = rth.index.normalize()
    g = rth.groupby(dates)

    sess = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
        "n_bars": g["close"].count(),
        "first_bar": g.apply(lambda x: x.index.min(), include_groups=False),
        "last_bar": g.apply(lambda x: x.index.max(), include_groups=False),
    })
    sess.index.name = "date"
    # half-day detection: last bar before 14:00
    sess["is_half_day"] = sess["last_bar"].dt.time < pd.Timestamp("14:00").time()

    # daily references, strictly prior
    sess["prev_close"] = sess["close"].shift(1)
    tr = np.maximum(sess["high"], sess["prev_close"]) - np.minimum(sess["low"], sess["prev_close"])
    sess["atr14"] = tr.rolling(14).mean().shift(1)
    ret = sess["close"].pct_change()
    sess["rv20"] = ret.rolling(20).std().shift(1) * np.sqrt(252)
    sess["sma200"] = sess["close"].rolling(200).mean().shift(1)
    sess["gap"] = sess["open"] / sess["prev_close"] - 1.0
    return rth, sess


def load_all(refresh: bool = False):
    """Cached load -> (minute_rth, sessions)."""
    if not refresh and os.path.exists(CACHE):
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    m = load_minute()
    rth, sess = build_sessions(m)
    with open(CACHE, "wb") as f:
        pickle.dump((rth, sess), f, protocol=4)
    return rth, sess


def day_arrays(minute_rth: pd.DataFrame):
    """Split RTH minutes into per-day numpy arrays for fast simulation.

    Returns dict: date -> dict(times [minutes since midnight], o, h, l, c, v)
    """
    out = {}
    dates = minute_rth.index.normalize()
    idx_min = minute_rth.index.hour * 60 + minute_rth.index.minute
    o = minute_rth["open"].to_numpy()
    h = minute_rth["high"].to_numpy()
    l = minute_rth["low"].to_numpy()
    c = minute_rth["close"].to_numpy()
    v = minute_rth["volume"].to_numpy(dtype=float)
    tmin = idx_min.to_numpy()
    # group boundaries
    d = dates.to_numpy()
    change = np.nonzero(d[1:] != d[:-1])[0] + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(d)]])
    for s, e in zip(starts, ends):
        out[pd.Timestamp(d[s])] = {
            "t": tmin[s:e], "o": o[s:e], "h": h[s:e], "l": l[s:e],
            "c": c[s:e], "v": v[s:e],
        }
    return out
