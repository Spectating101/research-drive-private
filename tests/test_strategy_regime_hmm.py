from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.regime_hmm import HmmRegimeModel, fit_default_hmm


@pytest.fixture
def two_regime_series():
    """120-month series: 60 months of bull (μ=2%, σ=3%) then 60 of bear (μ=-1%, σ=6%)."""
    rng = np.random.default_rng(0)
    bull = rng.normal(0.02, 0.03, size=60)
    bear = rng.normal(-0.01, 0.06, size=60)
    rets = np.concatenate([bull, bear])
    idx = pd.date_range("2010-01-31", periods=120, freq="ME")
    return pd.Series(rets, index=idx)


def test_hmm_fit_basic(two_regime_series):
    model = HmmRegimeModel(n_states=2, use_vol_feature=True, vol_window=6, seed=0).fit(two_regime_series)
    means = model.state_means()
    # state_0 is "bear" (lowest expected return); state_1 is "bull"
    assert means.loc["state_0", "return"] < means.loc["state_1", "return"]
    # Expected returns roughly match true regime means
    assert means.loc["state_1", "return"] > 0.01
    assert means.loc["state_0", "return"] < 0.01


def test_hmm_recovers_regime_transition(two_regime_series):
    """The most-likely state path should put the bear period in state 0 majority."""
    model = HmmRegimeModel(n_states=2, use_vol_feature=False, vol_window=6, seed=0).fit(two_regime_series)
    states = model.most_likely()
    bull_period_states = states.iloc[:60]
    bear_period_states = states.iloc[60:]
    # Majority of bull rows should be state_1, majority of bear rows state_0
    assert (bull_period_states == 1).mean() > 0.65
    assert (bear_period_states == 0).mean() > 0.65


def test_hmm_posterior_sums_to_one(two_regime_series):
    model = HmmRegimeModel(n_states=2, use_vol_feature=True, vol_window=6, seed=0).fit(two_regime_series)
    post = model.posterior()
    row_sums = post.sum(axis=1).values
    assert np.allclose(row_sums, 1.0, atol=1e-6)


def test_hmm_rejects_too_few_observations():
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(0, 0.01, 10), index=pd.date_range("2026-01-31", periods=10, freq="ME"))
    with pytest.raises(ValueError, match="at least"):
        HmmRegimeModel(n_states=2, use_vol_feature=False, vol_window=6, seed=0).fit(s)


def test_hmm_blend_params_blends_between_states(two_regime_series):
    """Blended values must lie on the convex hull of per-state values, and the
    bear-period asof must blend strictly more 'bear-ward' than a bull-period asof.
    Absolute thresholds are seed-fragile; relative ordering is not."""
    model = HmmRegimeModel(n_states=2, use_vol_feature=False, vol_window=6, seed=0).fit(two_regime_series)
    params_bear = {"target_vol": 0.05, "max_crypto_gross": 0.0}
    params_bull = {"target_vol": 0.20, "max_crypto_gross": 0.50}

    end_blend = model.blend_params(asof=two_regime_series.index[-1],
                                    params_per_state=[params_bear, params_bull])
    bull_blend = model.blend_params(asof=two_regime_series.index[29],
                                     params_per_state=[params_bear, params_bull])

    # Both blends are convex combinations of the state values
    for blend in (end_blend, bull_blend):
        assert params_bear["target_vol"] <= blend["target_vol"] <= params_bull["target_vol"]
        assert params_bear["max_crypto_gross"] <= blend["max_crypto_gross"] <= params_bull["max_crypto_gross"]

    # The bear-period asof must put strictly less weight on bull-params than
    # a deep-bull-period asof.
    assert end_blend["target_vol"] < bull_blend["target_vol"]
    assert end_blend["max_crypto_gross"] < bull_blend["max_crypto_gross"]


def test_hmm_blend_params_rejects_mismatched_state_count(two_regime_series):
    model = HmmRegimeModel(n_states=2, use_vol_feature=False, vol_window=6, seed=0).fit(two_regime_series)
    with pytest.raises(ValueError, match="params dict per state"):
        model.blend_params(
            asof=two_regime_series.index[-1],
            params_per_state=[{"target_vol": 0.1}],  # only 1, need 2
        )


def test_hmm_blend_params_rejects_missing_keys(two_regime_series):
    model = HmmRegimeModel(n_states=2, use_vol_feature=False, vol_window=6, seed=0).fit(two_regime_series)
    with pytest.raises(ValueError, match="missing keys"):
        model.blend_params(
            asof=two_regime_series.index[-1],
            params_per_state=[{"a": 1.0}, {"b": 2.0}],
        )


def test_fit_default_hmm_three_state(two_regime_series):
    model = fit_default_hmm(two_regime_series, n_states=3, seed=0)
    means = model.state_means()
    # Ordered: state_0 lowest, state_2 highest expected return
    assert means.loc["state_0", "return"] <= means.loc["state_1", "return"] <= means.loc["state_2", "return"]
    assert "vol" in means.columns


def test_hmm_state_ordering_is_deterministic_across_seeds(two_regime_series):
    """Different EM inits should still produce bear→bull ordering after reorder."""
    m1 = HmmRegimeModel(n_states=2, use_vol_feature=True, vol_window=6, seed=1).fit(two_regime_series)
    m2 = HmmRegimeModel(n_states=2, use_vol_feature=True, vol_window=6, seed=99).fit(two_regime_series)
    means1 = m1.state_means()
    means2 = m2.state_means()
    # state_0 must be the lower-return one in both
    assert means1.loc["state_0", "return"] < means1.loc["state_1", "return"]
    assert means2.loc["state_0", "return"] < means2.loc["state_1", "return"]
