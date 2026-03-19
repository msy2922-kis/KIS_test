"""
KRW KTB (국고채) Yield Curve Bootstrapper
==========================================
Bootstraps zero curve from Korean Treasury Bond (국고채) par yields.

Output: Zero Rates, Discount Factors, Forward Rates at any tenor.

Market conventions (KRW KTB):
  - Day count : Actual/365 Fixed
  - Coupon    : Semi-annual payments (6M intervals)
  - Yield     : Annual par yield; each coupon = yield * dcf(period, ACT/365)
  - Short end : 3M and/or 6M simple interest zero rates (단리)

Bootstrapping approach:
  - Short end (3M, 6M): DF = 1 / (1 + rate * t)  [simple interest / 단리]
  - 7M+  : Market par yields linearly interpolated to fill all 6M-step tenors,
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
    short_quotes: Optional[Dict[str, float]] = None,
) -> List[Tuple[date, float]]:
    """
    Return a list of (maturity_date, par_yield) pairs covering every 6M step
    from 6M to the maximum quoted tenor.

    Missing 6M-step tenors are linearly interpolated from market quotes.
    short_quotes (e.g. {'3M': 0.035, '6M': 0.036}) are used as lower anchors
    for interpolation.
    """
    known: Dict[float, float] = {}

    # Optional short-end anchors (3M, 6M simple interest rates as interpolation anchors)
    for tenor, rate in (short_quotes or {}).items():
        mat = add_tenor(valuation, tenor)
        t = (mat - valuation).days / 365.0
        known[round(t, 6)] = rate

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
    short_rate_3m : float, optional
        3M simple interest rate (단리, e.g. 3M Treasury bill yield).
    short_rate_6m : float, optional
        6M simple interest rate (단리, e.g. 6M Treasury bill yield).
    """

    DAY_COUNT = "ACT/365"

    def __init__(
        self,
        valuation_date: date,
        bond_quotes: Dict[str, float],
        short_rate_3m: Optional[float] = None,
        short_rate_6m: Optional[float] = None,
    ):
        super().__init__(valuation_date, name="KRW_KTB")
        self._bond_quotes = bond_quotes
        self._short_rate_3m = short_rate_3m
        self._short_rate_6m = short_rate_6m
        self._bootstrap()

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        val = self.valuation_date

        pillar_times: List[float] = []
        pillar_dfs: List[float] = []
        simple_interest_times: List[float] = []

        # 1) Short end: simple interest DFs (단리) — 3M then 6M
        for tenor, rate in [("3M", self._short_rate_3m), ("6M", self._short_rate_6m)]:
            if rate is not None:
                mat = add_tenor(val, tenor)
                t = (mat - val).days / 365.0
                df = 1.0 / (1.0 + rate * t)
                pillar_times.append(t)
                pillar_dfs.append(df)
                simple_interest_times.append(t)

        if pillar_times:
            self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

        # 2) Semi-annual coupon bond bootstrap
        short_quotes: Dict[str, float] = {}
        if self._short_rate_3m is not None:
            short_quotes["3M"] = self._short_rate_3m
        if self._short_rate_6m is not None:
            short_quotes["6M"] = self._short_rate_6m

        semiannual_pillars = _fill_semiannual_tenors(
            self._bond_quotes, val, short_quotes or None
        )

        for mat, par_yield in semiannual_pillars:
            t_check = (mat - val).days / 365.0
            # Skip pillars already set as simple interest (e.g. 6M)
            if any(abs(t_check - s) < 1e-4 for s in simple_interest_times):
                continue
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
