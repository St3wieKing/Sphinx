"""Scorecard metrics.

Primary per-trade unit: NET basis points of entry price (scale-free
across 26 years of price levels).  R-multiples reported when a stop
exists.  Portfolio-level curves use risk-based sizing:
    shares = equity * risk_frac / stop_distance, capped at lev_cap * equity notional
(no stop -> notional = lev_cap-limited fixed fraction).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def trades_frame(trades) -> pd.DataFrame:
    rows = []
    for tr in trades:
        rows.append({
            "date": tr.date, "direction": tr.direction,
            "entry_time": tr.entry_time, "exit_time": tr.exit_time,
            "entry_px": tr.entry_px, "exit_px": tr.exit_px,
            "entry_px_raw": tr.entry_px_raw, "exit_px_raw": tr.exit_px_raw,
            "exit_reason": tr.exit_reason,
            "pnl_ps": tr.pnl_per_share,
            "ret": tr.ret,
            "bps": tr.ret * 1e4,
            "risk_ps": tr.risk_per_share,
            "r_mult": tr.r_multiple,
        })
    return pd.DataFrame(rows)


def equity_curve(tf: pd.DataFrame, risk_frac=0.01, lev_cap=4.0, start=1.0):
    """Compound equity with risk sizing; returns (equity_series, daily_ret)."""
    if tf.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    eq = start
    dates, eqs, drets = [], [], []
    for _, r in tf.sort_values("date").iterrows():
        if r["risk_ps"] and r["risk_ps"] > 0:
            frac_at_risk_per_1 = r["risk_ps"] / r["entry_px_raw"]
            notional_frac = min(risk_frac / frac_at_risk_per_1, lev_cap)
        else:
            notional_frac = 1.0
        dr = notional_frac * r["ret"]
        eq *= (1.0 + dr)
        dates.append(r["date"]); eqs.append(eq); drets.append(dr)
    s = pd.Series(eqs, index=pd.DatetimeIndex(dates))
    return s, pd.Series(drets, index=pd.DatetimeIndex(dates))


def max_drawdown(eq: pd.Series) -> float:
    if eq.empty:
        return 0.0
    peak = eq.cummax()
    return float((eq / peak - 1.0).min())


def scorecard(tf: pd.DataFrame, sessions_in_period: int = None,
              risk_frac=0.01, lev_cap=4.0) -> dict:
    if tf.empty:
        return {"trades": 0}
    wins = tf[tf["bps"] > 0]
    losses = tf[tf["bps"] <= 0]
    exp_bps = tf["bps"].mean()
    sd = tf["bps"].std(ddof=1)
    n = len(tf)
    tstat = exp_bps / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    pf = wins["bps"].sum() / abs(losses["bps"].sum()) if len(losses) and losses["bps"].sum() != 0 else float("inf")
    eq, drets = equity_curve(tf, risk_frac, lev_cap)
    # daily Sharpe (trades are one-per-day max in all candidates)
    ann = 252
    sharpe = (drets.mean() / drets.std(ddof=1) * math.sqrt(ann)) if len(drets) > 2 and drets.std(ddof=1) > 0 else float("nan")
    years = max((tf["date"].max() - tf["date"].min()).days / 365.25, 1e-9)
    out = {
        "trades": n,
        "trades_per_year": n / years,
        "win_rate": len(wins) / n,
        "avg_win_bps": wins["bps"].mean() if len(wins) else 0.0,
        "avg_loss_bps": losses["bps"].mean() if len(losses) else 0.0,
        "expectancy_bps": exp_bps,
        "median_bps": tf["bps"].median(),
        "t_stat": tstat,
        "profit_factor": pf,
        "sharpe": sharpe,
        "max_dd": max_drawdown(eq),
        "cagr": eq.iloc[-1] ** (1 / years) - 1 if len(eq) else 0.0,
        "avg_R": tf["r_mult"].mean() if tf["r_mult"].notna().any() else float("nan"),
        "stop_rate": (tf["exit_reason"] == "stop").mean(),
        "eod_rate": (tf["exit_reason"].isin(["eod", "time"])).mean(),
    }
    if sessions_in_period:
        out["participation"] = n / sessions_in_period
    return out


def by_year(tf: pd.DataFrame) -> pd.DataFrame:
    if tf.empty:
        return pd.DataFrame()
    g = tf.groupby(pd.DatetimeIndex(tf["date"]).year)
    return pd.DataFrame({
        "trades": g.size(),
        "exp_bps": g["bps"].mean(),
        "sum_bps": g["bps"].sum(),
        "win_rate": g.apply(lambda x: (x["bps"] > 0).mean(), include_groups=False),
    })


def by_regime(tf: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """Regimes: rv20 terciles (computed on the analysis period) x trend."""
    if tf.empty:
        return pd.DataFrame()
    t = tf.copy()
    t["date"] = pd.DatetimeIndex(t["date"])
    s = sessions.loc[sessions.index.isin(t["date"])]
    rv = s["rv20"]
    q1, q2 = rv.quantile([1 / 3, 2 / 3])
    def vol_bucket(d):
        v = sessions.loc[d, "rv20"]
        return "low_vol" if v <= q1 else ("mid_vol" if v <= q2 else "high_vol")
    t["vol_regime"] = t["date"].map(vol_bucket)
    t["trend"] = t["date"].map(lambda d: "above_200sma" if sessions.loc[d, "close"] > sessions.loc[d, "sma200"] else "below_200sma")
    rows = []
    for key, grp in t.groupby(["vol_regime"]):
        rows.append({"regime": key[0], "trades": len(grp), "exp_bps": grp["bps"].mean(),
                     "win_rate": (grp["bps"] > 0).mean(), "sum_bps": grp["bps"].sum()})
    for key, grp in t.groupby(["trend"]):
        rows.append({"regime": key[0], "trades": len(grp), "exp_bps": grp["bps"].mean(),
                     "win_rate": (grp["bps"] > 0).mean(), "sum_bps": grp["bps"].sum()})
    return pd.DataFrame(rows)


def monte_carlo_dd(tf: pd.DataFrame, n_paths=2000, risk_frac=0.01, lev_cap=4.0, seed=7):
    """Bootstrap trade-order resampling -> drawdown / streak distributions."""
    if tf.empty:
        return {}
    rng = np.random.default_rng(seed)
    rets = []
    for _, r in tf.iterrows():
        if r["risk_ps"] and r["risk_ps"] > 0:
            nf = min(risk_frac / (r["risk_ps"] / r["entry_px_raw"]), lev_cap)
        else:
            nf = 1.0
        rets.append(nf * r["ret"])
    rets = np.array(rets)
    dds, streaks = [], []
    for _ in range(n_paths):
        x = rng.choice(rets, size=len(rets), replace=True)
        eq = np.cumprod(1 + x)
        peak = np.maximum.accumulate(eq)
        dds.append((eq / peak - 1).min())
        is_loss = x <= 0
        best = cur = 0
        for b in is_loss:
            cur = cur + 1 if b else 0
            best = max(best, cur)
        streaks.append(best)
    dds = np.array(dds); streaks = np.array(streaks)
    return {
        "dd_p50": float(np.percentile(dds, 50)),
        "dd_p95": float(np.percentile(dds, 5)),   # worse tail (more negative)
        "dd_p99": float(np.percentile(dds, 1)),
        "streak_p50": float(np.percentile(streaks, 50)),
        "streak_p95": float(np.percentile(streaks, 95)),
        "streak_max": int(streaks.max()),
    }
