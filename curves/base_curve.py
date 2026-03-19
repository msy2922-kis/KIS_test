"""
Base class for bootstrapped interest rate curves.
Stores zero rates and discount factors on a time grid,
and provides query methods for any tenor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import date
from typing import List, Tuple

from utils.interpolation import monotone_convex_df


class IRCurve:
    """
    Generic bootstrapped IR curve.

    Internally stores:
        _times  : year-fractions from valuation date (sorted)
        _dfs    : discount factors P(0, t)

    Zero rates and forward rates are derived on demand.
    """

    def __init__(self, valuation_date: date, name: str = "IRCurve"):
        self.valuation_date = valuation_date
        self.name = name
        self._times: np.ndarray = np.array([0.0])
        self._dfs: np.ndarray = np.array([1.0])

    # ------------------------------------------------------------------
    # Internal builders (called by subclass bootstrappers)
    # ------------------------------------------------------------------

    def _set_pillars(self, times: List[float], dfs: List[float]) -> None:
        """Store bootstrapped pillar times and discount factors."""
        t = np.array([0.0] + list(times))
        d = np.array([1.0] + list(dfs))
        # ensure sorted
        order = np.argsort(t)
        self._times = t[order]
        self._dfs = d[order]

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def discount_factor(self, t: float | np.ndarray) -> np.ndarray:
        """
        Interpolated discount factor P(0, t).
        t: year-fraction(s) from valuation date.
        """
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return monotone_convex_df(self._times, self._dfs, t)

    def zero_rate(self, t: float | np.ndarray, compounding: str = "continuous") -> np.ndarray:
        """
        Zero rate at maturity t (year-fraction).

        compounding:
            'continuous' : r = -ln(DF) / t
            'simple'     : r = (1/DF - 1) / t
            'annual'     : r = DF^(-1/t) - 1
        """
        t = np.atleast_1d(np.asarray(t, dtype=float))
        df = self.discount_factor(t)

        with np.errstate(divide="ignore", invalid="ignore"):
            if compounding == "continuous":
                r = np.where(t > 1e-10, -np.log(df) / t, 0.0)
            elif compounding == "simple":
                r = np.where(t > 1e-10, (1.0 / df - 1.0) / t, 0.0)
            elif compounding == "annual":
                r = np.where(t > 1e-10, df ** (-1.0 / t) - 1.0, 0.0)
            else:
                raise ValueError(f"Unknown compounding: {compounding}")
        return r

    def forward_rate(
        self,
        t1: float | np.ndarray,
        t2: float | np.ndarray,
        compounding: str = "continuous",
    ) -> np.ndarray:
        """
        Simply-compounded or continuously-compounded forward rate f(t1, t2).

        compounding:
            'continuous' : f = (z(t2)*t2 - z(t1)*t1) / (t2 - t1)
            'simple'     : f = (DF(t1)/DF(t2) - 1) / (t2 - t1)
        """
        t1 = np.atleast_1d(np.asarray(t1, dtype=float))
        t2 = np.atleast_1d(np.asarray(t2, dtype=float))
        dt = t2 - t1

        df1 = self.discount_factor(t1)
        df2 = self.discount_factor(t2)

        with np.errstate(divide="ignore", invalid="ignore"):
            if compounding == "continuous":
                f = np.where(dt > 1e-10, np.log(df1 / df2) / dt, 0.0)
            elif compounding == "simple":
                f = np.where(dt > 1e-10, (df1 / df2 - 1.0) / dt, 0.0)
            else:
                raise ValueError(f"Unknown compounding: {compounding}")
        return f

    # ------------------------------------------------------------------
    # Summary / display
    # ------------------------------------------------------------------

    def summary(self, tenors_yr: List[float] | None = None) -> pd.DataFrame:
        """
        Return a DataFrame with Zero Rate (%), Discount Factor, Forward Rate (%)
        for a list of year-fraction tenors.

        Forward rate is the instantaneous 3-month forward (t, t+0.25).
        """
        if tenors_yr is None:
            tenors_yr = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]

        t = np.array(tenors_yr)
        zr = self.zero_rate(t, compounding="continuous") * 100
        df = self.discount_factor(t)
        # 3-month forward rate starting at each t
        fwd = self.forward_rate(t, t + 0.25, compounding="simple") * 100

        labels = []
        for tv in tenors_yr:
            if tv < 1:
                labels.append(f"{int(round(tv*12))}M")
            else:
                labels.append(f"{int(tv)}Y")

        return pd.DataFrame(
            {"Tenor": labels, "Zero Rate (%)": zr, "Discount Factor": df,
             "3M Fwd Rate (%)": fwd}
        ).set_index("Tenor")

    def __repr__(self) -> str:
        return f"<{self.name} | valuation={self.valuation_date} | pillars={len(self._times)-1}>"
