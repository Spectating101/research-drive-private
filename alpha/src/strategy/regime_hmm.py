"""
Hidden-Markov-Model regime model for the alpha strategy.

The existing regime_policy.py is binary and mechanical: trailing trend / vol /
drawdown thresholds flip a switch. That misses partial regimes ("it's drifting
into a high-vol state, not there yet") and is sample-noisy at the boundary.

This HMM upgrade:

  - Fits a Gaussian HMM (2 or 3 states) on benchmark monthly returns,
    optionally augmented with realized vol as a second feature.
  - At each `asof`, exposes the posterior P(state_k | observations) so
    callers can *blend* parameters across regimes instead of flipping.
  - Auto-orders states by expected return so state-0 is bear and
    state-(K-1) is bull, regardless of EM init.

Designed to drop in alongside `compute_regime_metrics` / `policy_params`,
not replace them — caller chooses which regime layer to use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Model + helpers
# ---------------------------------------------------------------------------


@dataclass
class HmmRegimeModel:
    """
    Wrapper around hmmlearn.hmm.GaussianHMM with deterministic state ordering
    (state 0 = lowest expected return = "bear"; state K-1 = "bull").
    """

    n_states: int
    use_vol_feature: bool
    vol_window: int
    seed: int

    def __post_init__(self):
        self._fit_dates: Optional[pd.DatetimeIndex] = None
        self._X_train: Optional[np.ndarray] = None
        self._model = None  # populated by fit()
        self._state_order: Optional[np.ndarray] = None

    # -- public API ---------------------------------------------------------

    def fit(self, returns: pd.Series) -> "HmmRegimeModel":
        """Fit the HMM on a monthly return series."""
        from hmmlearn.hmm import GaussianHMM

        r = returns.dropna().sort_index()
        if len(r) < max(24, self.n_states * 12):
            raise ValueError(
                f"need at least {max(24, self.n_states * 12)} monthly returns; got {len(r)}"
            )

        X = self._build_features(r)
        model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=200,
            random_state=self.seed,
            tol=1e-4,
        )
        model.fit(X)
        # Re-order states by their per-state expected first-feature mean
        means_first = np.asarray(model.means_)[:, 0]
        order = np.argsort(means_first)  # ascending → state 0 is the bearest
        self._state_order = order
        self._model = model
        self._fit_dates = r.index
        self._X_train = X
        return self

    def posterior(self, returns: Optional[pd.Series] = None) -> pd.DataFrame:
        """
        Return P(state_k | obs) per period as a DataFrame with the
        re-ordered (bear→bull) columns ['state_0', ..., 'state_{K-1}'].

        If `returns` is None, uses the training data.
        """
        if self._model is None:
            raise RuntimeError("HMM not fit yet — call fit() first")
        if returns is None:
            X = self._X_train
            idx = self._fit_dates
        else:
            r = returns.dropna().sort_index()
            X = self._build_features(r)
            idx = r.index
        post = self._model.predict_proba(X)  # (T, K) in original state order
        # Reindex columns into bear→bull order
        post_ordered = post[:, self._state_order]
        return pd.DataFrame(
            post_ordered,
            index=idx,
            columns=[f"state_{k}" for k in range(self.n_states)],
        )

    def most_likely(self, returns: Optional[pd.Series] = None) -> pd.Series:
        """Return the Viterbi-most-likely state per period, in bear→bull order."""
        post = self.posterior(returns=returns)
        return post.idxmax(axis=1).str.replace("state_", "").astype(int)

    def blend_params(
        self,
        *,
        asof: pd.Timestamp,
        params_per_state: Sequence[Dict[str, float]],
        returns: Optional[pd.Series] = None,
    ) -> Dict[str, float]:
        """
        Weighted-blend a parameter dict across states by posterior probability.

        params_per_state[k] is the dict to apply if we're in state k (with
        state 0 = bear, K-1 = bull). Each dict must have the same keys.

        Returns a dict where value[key] = Σ_k P(state_k|asof) * params_per_state[k][key].
        """
        if len(params_per_state) != self.n_states:
            raise ValueError(
                f"need one params dict per state ({self.n_states}); got {len(params_per_state)}"
            )
        post = self.posterior(returns=returns)
        # Use the row at or just before asof
        asof = pd.Timestamp(asof)
        eligible = post.loc[post.index <= asof]
        if eligible.empty:
            raise ValueError(f"no observations at or before {asof}")
        probs = eligible.iloc[-1].values

        keys = set(params_per_state[0].keys())
        for d in params_per_state:
            missing = keys - set(d.keys())
            if missing:
                raise ValueError(f"param dict missing keys: {sorted(missing)}")

        blended = {}
        for k in sorted(keys):
            vals = np.array([float(d[k]) for d in params_per_state], dtype=float)
            blended[k] = float(np.dot(probs, vals))
        return blended

    # -- internals ----------------------------------------------------------

    def _build_features(self, r: pd.Series) -> np.ndarray:
        cols = [r.values.reshape(-1, 1)]
        if self.use_vol_feature:
            vol = r.rolling(self.vol_window, min_periods=max(2, self.vol_window // 2)).std()
            vol = vol.bfill().values.reshape(-1, 1)
            cols.append(vol)
        return np.hstack(cols).astype(float)

    def state_means(self) -> pd.DataFrame:
        """Per-state mean of each feature, in bear→bull order."""
        if self._model is None:
            raise RuntimeError("HMM not fit yet — call fit() first")
        means = np.asarray(self._model.means_)[self._state_order]
        feat_names = ["return"] + (["vol"] if self.use_vol_feature else [])
        return pd.DataFrame(means, columns=feat_names, index=[f"state_{k}" for k in range(self.n_states)])


def fit_default_hmm(returns: pd.Series, *, n_states: int = 3, seed: int = 42) -> HmmRegimeModel:
    """Convenience: 3-state Gaussian HMM on (return, rolling-vol)."""
    model = HmmRegimeModel(n_states=n_states, use_vol_feature=True, vol_window=12, seed=seed)
    model.fit(returns)
    return model


# ---------------------------------------------------------------------------
# CLI: fit HMM on a benchmark return series, print regime path + blend demo
# ---------------------------------------------------------------------------


def _cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Fit + inspect a Gaussian HMM regime model.")
    ap.add_argument("--returns-csv", type=Path, required=True,
                    help="CSV with date,return columns; monthly frequency.")
    ap.add_argument("--n-states", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-vol", action="store_true")
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args(argv)

    df = pd.read_csv(args.returns_csv)
    if "date" not in df.columns or "return" not in df.columns:
        raise SystemExit("--returns-csv must have date,return columns")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    s = df.dropna().set_index("date")["return"].astype(float)

    model = HmmRegimeModel(
        n_states=args.n_states,
        use_vol_feature=not args.no_vol,
        vol_window=12,
        seed=args.seed,
    ).fit(s)

    post = model.posterior()
    out = {
        "n_states": args.n_states,
        "use_vol_feature": not args.no_vol,
        "n_obs": int(len(s)),
        "state_means": model.state_means().to_dict(orient="index"),
        "latest_posterior": post.iloc[-1].to_dict(),
        "regime_path_recent": post.tail(12).to_dict(orient="index"),
    }
    try:
        from src.research.fingerprint import stamp as _stamp_fp
        _stamp_fp(out, config={"args": vars(args)})
    except Exception:
        pass
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(text + "\n")
        print(f"\nwrote: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
