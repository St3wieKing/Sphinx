import pytest

from sphinx.backtest.costs import CostModel
from sphinx.risk.sizing import notional_fraction, shares_for
from sphinx.risk.limits import RiskState

CFG = {
    "sizing": {"risk_budget_frac": 0.005, "risk_proxy_atr_mult": 0.30, "leverage_cap": 2.0},
    "risk_limits": {"max_daily_loss_frac": 0.015, "max_20trade_loss_frac": 0.06,
                    "max_position_notional_frac": 2.0, "max_consecutive_data_failures": 3},
}


def test_cost_per_side_base():
    cm = CostModel()
    assert abs(cm.per_side - 0.0135) < 1e-12


def test_cost_stress_scales_market_costs_not_commission():
    cm = CostModel(stress=2.0)
    assert abs(cm.per_side - (0.0035 + 2 * 0.010)) < 1e-12


def test_entry_exit_adverse_signs():
    cm = CostModel()
    assert cm.entry_price(100.0, 1) > 100.0        # long pays up
    assert cm.entry_price(100.0, -1) < 100.0       # short sells down
    assert cm.exit_price(100.0, 1) < 100.0         # long exit receives less
    assert cm.exit_price(100.0, 1, is_stop=True) < cm.exit_price(100.0, 1)


def test_sizing_vol_scaling_and_cap():
    # ATR% = 1% -> frac = 0.005/(0.3*0.01) = 1.667 < cap
    f = notional_fraction(1.0, 100.0, CFG)
    assert abs(f - 5 / 3) < 1e-9
    # very low vol would breach cap -> capped at 2
    assert notional_fraction(0.1, 100.0, CFG) == 2.0


def test_shares_floor_and_zero_guards():
    assert shares_for(100_000, 500.0, 5.0, 500.0, CFG) == 333  # frac=5/3 -> 166.7k/500
    assert shares_for(0, 500.0, 5.0, 500.0, CFG) == 0
    assert shares_for(100_000, 0.0, 5.0, 500.0, CFG) == 0


def test_daily_loss_lockout():
    rs = RiskState()
    rs.record_trade(-0.016, CFG)
    assert not rs.can_trade()
    rs.new_session()
    assert rs.can_trade()


def test_rolling20_hard_lock_survives_new_session():
    rs = RiskState()
    for _ in range(20):
        rs.record_trade(-0.004, CFG)
    assert rs.locked_hard and not rs.can_trade()
    rs.new_session()
    assert not rs.can_trade()  # hard lock persists


def test_data_failure_lockout():
    rs = RiskState()
    for _ in range(3):
        rs.record_data_failure(CFG)
    assert not rs.can_trade()
