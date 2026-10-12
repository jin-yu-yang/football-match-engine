import pytest

from matchlab.stats import bootstrap_mean_ci, mean, wilson_interval


def test_wilson_known_values():
    lo, hi = wilson_interval(7, 10)
    assert lo == pytest.approx(0.396778, abs=1e-6)
    assert hi == pytest.approx(0.892209, abs=1e-6)
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    assert wilson_interval(0, 7)[0] == 0.0 and wilson_interval(10, 10)[1] == 1.0
    assert wilson_interval(0, 0) is None


def test_mean():
    assert mean([1, 2, 3]) == 2
    assert mean([]) is None


def test_bootstrap_constant_values():
    assert bootstrap_mean_ci([1.0, 1.0, 1.0]) == [1.0, 1.0]


def test_bootstrap_is_deterministic_and_brackets_mean():
    values = [0, 1, 2, 3, -1, 2, 1]
    first = bootstrap_mean_ci(values)
    assert first == bootstrap_mean_ci(values)
    assert first[0] <= mean(values) <= first[1]
    assert bootstrap_mean_ci([]) is None
