import numpy as np
import pytest

from sphinx.execution.fills import stop_entry_fill, protective_stop_fill, target_fill


def test_stop_entry_long_gap_through_fills_at_open():
    assert stop_entry_fill(1, 100.0, 101.0, 102.0, 100.5) == 101.0


def test_stop_entry_long_touch_fills_at_stop():
    assert stop_entry_fill(1, 100.0, 99.0, 100.2, 98.9) == 100.0


def test_stop_entry_no_fill():
    assert stop_entry_fill(1, 100.0, 99.0, 99.5, 98.5) is None


def test_stop_entry_short():
    assert stop_entry_fill(-1, 100.0, 99.5, 99.9, 99.0) == 99.5  # gap through
    assert stop_entry_fill(-1, 100.0, 100.5, 100.9, 99.8) == 100.0


def test_protective_stop_long_gap_down_fills_at_open():
    assert protective_stop_fill(1, 95.0, 93.0, 94.0, 92.0) == 93.0


def test_protective_stop_long_touch():
    assert protective_stop_fill(1, 95.0, 96.0, 96.5, 94.9) == 95.0


def test_protective_stop_short():
    assert protective_stop_fill(-1, 105.0, 106.0, 107.0, 105.5) == 106.0
    assert protective_stop_fill(-1, 105.0, 104.0, 105.2, 103.9) == 105.0


def test_target_long():
    assert target_fill(1, 110.0, 111.0, 112.0, 110.5) == 111.0
    assert target_fill(1, 110.0, 109.0, 110.3, 108.9) == 110.0
    assert target_fill(1, 110.0, 109.0, 109.5, 108.9) is None
