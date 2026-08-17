"""Strategy fidelity + reproducibility tests (require the raw dataset;
skipped automatically when data is absent)."""
import os
import sys

import pytest

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "candles_1m.csv.gz")
needs_data = pytest.mark.skipif(not os.path.exists(DATA), reason="raw data not present")


@needs_data
def test_production_path_matches_research_candidate_2010_2011():
    """The frozen production signal path must select exactly the same trades
    (dates + directions) as the research candidate that won the tournament."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research"))
    import candidates as C
    from sphinx.backtest.run_strategy import run_frozen
    from sphinx.backtest.costs import CostModel
    from sphinx.backtest.engine import simulate_day
    from sphinx.config import load_config
    from sphinx.data.loader import load_all, day_arrays
    from sphinx.data.validation import valid_session_mask

    cfg = load_config()
    tf, _, _ = run_frozen("2010-01-01", "2011-12-31", cfg)

    rth, sessions = load_all()
    arrs = day_arrays(rth)
    mask = valid_session_mask(sessions)
    days = [d for d in sessions.index
            if "2010-01-01" <= str(d.date()) <= "2011-12-31"
            and mask.loc[d] and sessions.loc[d, "rv20"] >= cfg["signal"]["rv20_min"]]
    params = {"predictor": "both", "entry_time": 930, "min_move_frac": 0.10,
              "stop_atr": 2.0}
    research = []
    for d in days:
        plan = C.c5_intraday_momentum(d, arrs[d], sessions.loc[d], params)
        if plan:
            tr = simulate_day(d, arrs[d], plan, CostModel())
            if tr:
                research.append((d, tr.direction, round(tr.entry_px, 6), round(tr.exit_px, 6)))
    produced = list(zip(tf["date"], tf["direction"],
                        tf["entry_px_net"].round(6), tf["exit_px_net"].round(6)))
    assert produced == research


@needs_data
def test_backtest_reproducible():
    from sphinx.backtest.run_strategy import run_frozen
    tf1, _, eq1 = run_frozen("2012-01-01", "2012-12-31")
    tf2, _, eq2 = run_frozen("2012-01-01", "2012-12-31")
    assert eq1 == eq2
    assert tf1.equals(tf2)


@needs_data
def test_no_trades_on_half_days_or_low_vol():
    from sphinx.backtest.run_strategy import run_frozen
    from sphinx.config import load_config
    from sphinx.data.loader import load_all
    cfg = load_config()
    tf, _, _ = run_frozen("2003-01-02", "2014-12-31", cfg)
    _, sessions = load_all()
    for d in tf["date"]:
        assert not sessions.loc[d, "is_half_day"]
        assert sessions.loc[d, "rv20"] >= cfg["signal"]["rv20_min"]
