"""
KRW CD IRS Curve Bootstrapper
==============================
Bootstraps zero curve from:
  - Short end  : CD 91-day deposit rate (Act/365, simple interest)
  - Long end   : Par CD IRS fixed rates, Act/365, quarterly fixed payments

Output: Zero Rates, Discount Factors, Forward Rates at any tenor.

Market conventions (KRW CD IRS):
  - Day count : Actual/365 Fixed
  - Fixed leg : Quarterly payments (3M intervals)
  - Floating  : 91-day CD rate reset quarterly (approximated as par floater)
  - Business day adj: not applied (simplified – extend if needed)

Bootstrapping approach:
  - Market par rates are linearly interpolated to fill all quarterly tenors
    (3M, 6M, 9M, 1Y, 1Y3M, …) before bootstrapping so that every quarterly
    payment date is an exact pillar.
"""
from __future__ import annotations

import numpy as np
from datetime import date
from typing import Dict, List, Tuple

from curves.base_curve import IRCurve
from utils.day_count import dcf, add_tenor
from utils.interpolation import log_linear_df


# ---------------------------------------------------------------------------
# Helper: generate quarterly payment schedule
# ---------------------------------------------------------------------------

def _quarterly_schedule(valuation: date, maturity: date) -> List[date]:
    """Return quarterly payment dates from valuation+3M up to (and including) maturity."""
    dates: List[date] = []
    t = valuation
    while True:
        t = add_tenor(t, "3M")
        if t >= maturity:
            dates.append(maturity)
            break
        dates.append(t)
    return dates


# ---------------------------------------------------------------------------
# Helper: fill missing quarterly tenors by interpolating par rates
# ---------------------------------------------------------------------------

def _fill_quarterly_tenors(
    cd_rate: float,
    swap_quotes: Dict[str, float],
    valuation: date,
) -> List[Tuple[date, float]]:
    """
    Return a list of (maturity_date, par_rate) pairs covering every 3M step
    from 3M to the maximum quoted tenor.

    3M is anchored to the CD deposit rate.
    Missing quarterly tenors between quoted tenors are linearly interpolated.
    """
    # Build known data points: (year_fraction, rate)
    known: Dict[float, float] = {}

    # CD 3M anchor
    mat_3m = add_tenor(valuation, "3M")
    t_3m = (mat_3m - valuation).days / 365.0
    known[round(t_3m, 6)] = cd_rate

    for tenor, rate in swap_quotes.items():
        mat = add_tenor(valuation, tenor)
        t = (mat - valuation).days / 365.0
        known[round(t, 6)] = rate

    sorted_t = sorted(known.keys())
    max_t = sorted_t[-1]

    # Generate all quarterly maturities up to max_t
    result: List[Tuple[date, float]] = []
    step = valuation
    while True:
        step = add_tenor(step, "3M")
        t = (step - valuation).days / 365.0
        if t > max_t + 1e-6:
            break

        # Interpolate if not a known pillar
        if any(abs(t - s) < 1e-4 for s in sorted_t):
            # Find closest key
            closest = min(sorted_t, key=lambda s: abs(s - t))
            rate = known[closest]
        else:
            lowers = [s for s in sorted_t if s < t]
            uppers = [s for s in sorted_t if s > t]
            if not lowers:
                rate = known[sorted_t[0]]
            elif not uppers:
                rate = known[sorted_t[-1]]
            else:
                t0, t1 = max(lowers), min(uppers)
                r0, r1 = known[t0], known[t1]
                rate = r0 + (r1 - r0) * (t - t0) / (t1 - t0)

        result.append((step, rate))

    return result


# ---------------------------------------------------------------------------
# Main bootstrapper
# ---------------------------------------------------------------------------

class KRWCDCurve(IRCurve):
    """
    KRW CD IRS Curve.

    Parameters
    ----------
    valuation_date : date
        Curve valuation / reference date.
    cd_rate : float
        91-day CD rate as a decimal (e.g. 0.0350 = 3.50%).
    swap_quotes : dict
        Par CD IRS fixed rates. Keys are tenor strings (e.g. '6M', '1Y', '3Y').
        Values are rates as decimals.
    """

    DAY_COUNT = "ACT/365"

    def __init__(
        self,
        valuation_date: date,
        cd_rate: float,
        swap_quotes: Dict[str, float],
    ):
        super().__init__(valuation_date, name="KRW_CD_IRS")
        self._cd_rate = cd_rate
        self._swap_quotes = swap_quotes
        self._bootstrap()

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        val = self.valuation_date

        pillar_times: List[float] = []
        pillar_dfs: List[float] = []

        # Generate all quarterly tenors with interpolated par rates
        quarterly_pillars = _fill_quarterly_tenors(
            self._cd_rate, self._swap_quotes, val
        )

        for mat, par_rate in quarterly_pillars:
            schedule = _quarterly_schedule(val, mat)

            pv01_sum = 0.0
            prev_date = val
            for pay_date in schedule[:-1]:
                tau_i = dcf(prev_date, pay_date, self.DAY_COUNT)
                t_i = (pay_date - val).days / 365.0
                df_i = self.discount_factor(t_i)[0]
                pv01_sum += tau_i * df_i
                prev_date = pay_date

            last_pay = schedule[-1]
            tau_N = dcf(prev_date, last_pay, self.DAY_COUNT)
            t_N = (last_pay - val).days / 365.0

            df_N = (1.0 - par_rate * pv01_sum) / (1.0 + par_rate * tau_N)

            if df_N <= 0:
                t_str = f"{t_N:.2f}Y"
                raise RuntimeError(
                    f"Non-positive DF at {t_str}: DF={df_N:.6f}. Check input rates."
                )

            pillar_times.append(t_N)
            pillar_dfs.append(df_N)
            self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

    # ------------------------------------------------------------------
    # Convenience: par CD IRS rate implied by the curve
    # ------------------------------------------------------------------

    def par_swap_rate(self, tenor: str) -> float:
        """Fair fixed rate for a CD IRS of given tenor (curve validation)."""
        val = self.valuation_date
        mat = add_tenor(val, tenor)
        schedule = _quarterly_schedule(val, mat)

        annuity = 0.0
        prev_date = val
        for pay_date in schedule:
            tau_i = dcf(prev_date, pay_date, self.DAY_COUNT)
            t_i = (pay_date - val).days / 365.0
            annuity += tau_i * self.discount_factor(t_i)[0]
            prev_date = pay_date

        t_N = (mat - val).days / 365.0
        df_N = self.discount_factor(t_N)[0]
        return (1.0 - df_N) / annuity
