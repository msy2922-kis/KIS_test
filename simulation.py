"""
Monte Carlo Simulation Engine
==============================
Simulates short rate paths for any ShortRateModel.
"""

import numpy as np
from short_rate_models import ShortRateModel, HullWhiteModel, HoLeeModel


class MonteCarloSimulator:
    """
    Monte Carlo simulator for short rate models.

    Parameters
    ----------
    model : ShortRateModel
        Any instance of a ShortRateModel subclass.
    seed : int or None
        Random seed for reproducibility.
    """

    def __init__(self, model: ShortRateModel, seed: int = 42):
        self.model = model
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        T: float = 1.0,
        n_steps: int = 252,
        n_paths: int = 1000,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate Monte Carlo paths.

        Parameters
        ----------
        T : float
            Total simulation horizon (years).
        n_steps : int
            Number of time steps.
        n_paths : int
            Number of simulation paths.

        Returns
        -------
        times : np.ndarray, shape (n_steps+1,)
            Time grid [0, dt, 2dt, ..., T].
        paths : np.ndarray, shape (n_paths, n_steps+1)
            Simulated short rate paths.
        """
        dt = T / n_steps
        times = np.linspace(0, T, n_steps + 1)

        paths = np.empty((n_paths, n_steps + 1))
        paths[:, 0] = self.model.r0

        # Brownian increments: shape (n_steps, n_paths)
        dW = self.rng.standard_normal((n_steps, n_paths)) * np.sqrt(dt)

        # Check if model supports time-aware stepping
        time_aware = hasattr(self.model, "step_at")

        for i in range(n_steps):
            r_curr = paths[:, i]
            dW_i = dW[i]
            if time_aware:
                paths[:, i + 1] = self.model.step_at(r_curr, dt, dW_i, times[i])
            else:
                paths[:, i + 1] = self.model.step(r_curr, dt, dW_i)

        return times, paths

    def compute_statistics(
        self, paths: np.ndarray, percentiles: list[float] = (5, 25, 50, 75, 95)
    ) -> dict:
        """
        Compute descriptive statistics across paths at each time step.

        Parameters
        ----------
        paths : np.ndarray, shape (n_paths, n_steps+1)
        percentiles : list of float
            Percentiles to compute (0-100).

        Returns
        -------
        dict with keys: mean, std, min, max, and each percentile (e.g. 'p5', 'p50').
        """
        stats = {
            "mean": paths.mean(axis=0),
            "std": paths.std(axis=0),
            "min": paths.min(axis=0),
            "max": paths.max(axis=0),
        }
        for p in percentiles:
            stats[f"p{int(p)}"] = np.percentile(paths, p, axis=0)
        return stats

    def bond_price(self, paths: np.ndarray, dt: float) -> np.ndarray:
        """
        Estimate zero-coupon bond price P(0, T) via Monte Carlo.

        P(0, T) ≈ mean[ exp(-∑ r_i * dt) ]

        Parameters
        ----------
        paths : np.ndarray, shape (n_paths, n_steps+1)
        dt : float
            Time step size.

        Returns
        -------
        float
            Estimated bond price.
        """
        # Trapezoidal integration of rates along each path
        integral = np.trapezoid(paths, dx=dt, axis=1) if hasattr(np, "trapezoid") else np.trapz(paths, dx=dt, axis=1)
        discount_factors = np.exp(-integral)
        return discount_factors.mean()

    def term_structure(
        self,
        maturities: np.ndarray,
        n_steps_per_year: int = 252,
        n_paths: int = 2000,
    ) -> np.ndarray:
        """
        Compute zero-coupon yield curve from Monte Carlo.

        Parameters
        ----------
        maturities : np.ndarray
            Array of maturities (years) at which to compute yields.
        n_steps_per_year : int
            Time steps per year.
        n_paths : int
            Number of paths.

        Returns
        -------
        yields : np.ndarray
            Zero-coupon yields at each maturity.
        """
        yields = np.empty(len(maturities))
        for j, T in enumerate(maturities):
            n_steps = max(1, int(T * n_steps_per_year))
            dt = T / n_steps
            _, paths = self.simulate(T=T, n_steps=n_steps, n_paths=n_paths)
            price = self.bond_price(paths, dt)
            yields[j] = -np.log(price) / T if T > 0 else self.model.r0
        return yields

    def print_summary(self, times: np.ndarray, paths: np.ndarray) -> None:
        """Print a summary table of simulation statistics."""
        stats = self.compute_statistics(paths)
        dt = times[1] - times[0]
        T = times[-1]
        n_paths, n_steps_p1 = paths.shape

        print(f"\n{'='*60}")
        print(f"  Model: {self.model.name}")
        print(f"  Paths: {n_paths:,}  |  Steps: {n_steps_p1 - 1}  |  Horizon: {T:.1f}Y")
        print(f"  Initial rate: {self.model.r0:.4f} ({self.model.r0*100:.2f}%)")
        print(f"{'='*60}")
        print(f"{'Time':>6} {'Mean':>8} {'Std':>8} {'P5':>8} {'P50':>8} {'P95':>8}")
        print(f"{'-'*60}")

        # Print at ~10 evenly-spaced checkpoints
        indices = np.linspace(0, len(times) - 1, min(11, len(times)), dtype=int)
        for i in indices:
            t = times[i]
            print(
                f"{t:>6.2f} "
                f"{stats['mean'][i]*100:>7.3f}% "
                f"{stats['std'][i]*100:>7.3f}% "
                f"{stats['p5'][i]*100:>7.3f}% "
                f"{stats['p50'][i]*100:>7.3f}% "
                f"{stats['p95'][i]*100:>7.3f}%"
            )
        print(f"{'='*60}")

        # Bond price
        price = self.bond_price(paths, dt)
        yield_ = -np.log(price) / T if T > 0 else self.model.r0
        print(f"  Bond Price P(0,{T:.1f}Y): {price:.6f}")
        print(f"  Implied Yield:     {yield_*100:.4f}%")
        neg_rate_pct = (paths < 0).any(axis=1).mean() * 100
        print(f"  Paths with negative rates: {neg_rate_pct:.1f}%")
        print(f"{'='*60}\n")
