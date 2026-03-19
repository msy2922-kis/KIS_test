"""
KRW KTB (국고채) Yield Curve Bootstrapper
==========================================
Bootstraps zero curve from Korean Treasury Bond (국고채) par yields.

Output: Zero Rates, Discount Factors, Forward Rates at any tenor.

Market conventions (KRW KTB):
  - Day count : Actual/365 Fixed
  - Coupon    : Semi-annual payments (6M intervals)
  - Yield     : Annual par yield; each coupon = yield * dcf(period, ACT/365)
  - Short end : Sub-6M tenor (e.g. 3M T-bill) as simple interest zero rate

Bootstrapping approach:
  - Short end: DF = 1 / (1 + rate * t)  [simple interest]
  - 6M+ : Market par yields linearly interpolated to fill all 6M-step tenors,
           then sequential bootstrap from semi-annual coupon bond par yields.
"""
from __future__ import annotations

import numpy as np
from datetime import date
from typing import Dict, List, Optional, Tuple

from curves.base_curve import IRCurve
from utils.day_count import dcf, add_tenor
from utils.interpolation import log_linear_df


# ---------------------------------------------------------------------------
# Helper: generate semi-annual payment schedule
# ---------------------------------------------------------------------------

def _semiannual_schedule(valuation: date, maturity: date) -> List[date]:
    """Return semi-annual payment dates from valuation+6M up to (and including) maturity."""
    dates: List[date] = []
    t = valuation
    while True:
        t = add_tenor(t, "6M")
        if t >= maturity:
            dates.append(maturity)
            break
        dates.append(t)
    return dates


# ---------------------------------------------------------------------------
# Helper: fill missing semi-annual tenors by interpolating par yields
# ---------------------------------------------------------------------------

def _fill_semiannual_tenors(
    bond_quotes: Dict[str, float],
    valuation: date,
    short_rate: Optional[float] = None,
    short_tenor: str = "3M",
) -> List[Tuple[date, float]]:
    """
    Return a list of (maturity_date, par_yield) pairs covering every 6M step
    from 6M to the maximum quoted tenor.

    Missing 6M-step tenors are linearly interpolated from market quotes.
    If short_rate is provided, it is used as a lower anchor for interpolation.
    """
    known: Dict[float, float] = {}

    # Optional short-end anchor
    if short_rate is not None:
        mat_short = add_tenor(valuation, short_tenor)
        t_short = (mat_short - valuation).days / 365.0
        known[round(t_short, 6)] = short_rate

    for tenor, rate in bond_quotes.items():
        mat = add_tenor(valuation, tenor)
        t = (mat - valuation).days / 365.0
        known[round(t, 6)] = rate

    sorted_t = sorted(known.keys())

    # Determine the maximum KTB quote time (6M+)
    bond_ts = []
    for tenor in bond_quotes:
        mat = add_tenor(valuation, tenor)
        bond_ts.append((mat - valuation).days / 365.0)
    if not bond_ts:
        return []
    max_bond_t = max(bond_ts)

    result: List[Tuple[date, float]] = []
    step = valuation
    while True:
        step = add_tenor(step, "6M")
        t = (step - valuation).days / 365.0
        if t > max_bond_t + 1e-6:
            break

        if any(abs(t - s) < 1e-4 for s in sorted_t):
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

class KRWKTBCurve(IRCurve):
    """
    KRW KTB (국고채) Yield Curve.

    Bootstraps a zero curve from Korean Treasury Bond (국고채) par yields.

    Parameters
    ----------
    valuation_date : date
        Curve valuation / reference date.
    bond_quotes : dict
        KTB par yields keyed by tenor string (e.g. '1Y', '3Y', '10Y').
        Values are annual yields as decimals (e.g. 0.034 = 3.40%).
    short_rate : float, optional
        Short-end simple interest rate (e.g. 3M Treasury bill yield).
        Used as an anchor for sub-6M discount factors. If None, the curve
        starts at the shortest KTB tenor.
    short_tenor : str
        Tenor of the short_rate (default '3M').
    """

    DAY_COUNT = "ACT/365"

    def __init__(
        self,
        valuation_date: date,
        bond_quotes: Dict[str, float],
        short_rate: Optional[float] = None,
        short_tenor: str = "3M",
    ):
        super().__init__(valuation_date, name="KRW_KTB")
        self._bond_quotes = bond_quotes
        self._short_rate = short_rate
        self._short_tenor = short_tenor
        self._bootstrap()

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        val = self.valuation_date

        pillar_times: List[float] = []
        pillar_dfs: List[float] = []

        # 1) Short end: simple interest DF
        if self._short_rate is not None:
            mat = add_tenor(val, self._short_tenor)
            t = (mat - val).days / 365.0
            df = 1.0 / (1.0 + self._short_rate * t)
            pillar_times.append(t)
            pillar_dfs.append(df)
            self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

        # 2) Semi-annual coupon bond bootstrap
        semiannual_pillars = _fill_semiannual_tenors(
            self._bond_quotes, val, self._short_rate, self._short_tenor
        )

        for mat, par_yield in semiannual_pillars:
            schedule = _semiannual_schedule(val, mat)

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

            df_N = (1.0 - par_yield * pv01_sum) / (1.0 + par_yield * tau_N)

            if df_N <= 0:
                t_str = f"{t_N:.2f}Y"
                raise RuntimeError(
                    f"Non-positive DF at {t_str}: DF={df_N:.6f}. Check input rates."
                )

            pillar_times.append(t_N)
            pillar_dfs.append(df_N)
            self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

    # ------------------------------------------------------------------
    # Convenience: par KTB yield implied by the curve
    # ------------------------------------------------------------------

    def par_bond_yield(self, tenor: str) -> float:
        """Fair par yield for a KTB of given tenor (curve validation)."""
        val = self.valuation_date
        mat = add_tenor(val, tenor)
        schedule = _semiannual_schedule(val, mat)

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

    def par_swap_rate(self, tenor: str) -> float:
        """Alias for par_bond_yield (compatibility with validation utility)."""
        return self.par_bond_yield(tenor)
