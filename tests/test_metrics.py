import pytest

from backend.eval.metrics import (
    accuracy,
    expected_calibration_error,
    fit_calibration,
    win_rate,
)


def test_accuracy():
    assert accuracy([True, True, False, False]) == 0.5
    assert accuracy([]) == 0.0
    assert accuracy([True, True]) == 1.0


def test_win_rate_net():
    # candidate right where baseline wrong on item 0; baseline right where candidate wrong on item 2.
    cand = [True, True, False]
    base = [False, True, True]
    assert win_rate(cand, base) == pytest.approx((1 + 0 - 1) / 3)


def test_win_rate_requires_alignment():
    with pytest.raises(ValueError):
        win_rate([True], [True, False])


def test_ece_perfectly_calibrated_is_zero():
    # confidence 1.0 and always correct → no gap.
    assert expected_calibration_error([1.0, 1.0], [True, True]) == pytest.approx(0.0)


def test_ece_overconfident():
    # Two samples at confidence 0.9, one right one wrong → |0.5 - 0.9| = 0.4.
    assert expected_calibration_error([0.9, 0.9], [True, False]) == pytest.approx(0.4)


def test_fit_calibration_empirical_accuracy_per_grade():
    grades = ["A", "A", "B", "B"]
    correct = [True, False, True, True]
    assert fit_calibration(grades, correct) == {"A": 0.5, "B": 1.0}
