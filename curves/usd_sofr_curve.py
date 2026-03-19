"""
USD SOFR IRS Curve Bootstrapper
================================
Bootstraps zero curve from:
  - Short end  : SOFR OIS deposit rates (≤ 1Y), Act/360, simple compounding
  - Long end   : Par SOFR IRS fixed rates  (> 1Y), Act/360, annual fixed payments

Output: Zero Rates, Discount Factors, Forward Rates at any tenor.

Market conventions (USD SOFR IRS):
  - Day count : Actual/360
  - Fixed leg : Annual payments
  - Floating  : Daily compounded SOFR (approximated as par floater)
  - Business day adj: not applied (simplified – extend if needed)

Bootstrapping approach:
  - Market par rates are linearly interpolated to fill all integer-year tenors
    before bootstrapping.  This ensures every annual payment date is a
    bootstrapped pillar, eliminating interpolation errors at intermediate dates.
"""
from __future__ import annotations

import numpy as np
from datetime import date
from typing import Dict, List

from curves.base_curve import IRCurve
from utils.day_count import dcf, add_tenor
from utils.interpolation import log_linear_df


# ---------------------------------------------------------------------------
# Helper: generate annual payment schedule for a swap
# ---------------------------------------------------------------------------

def _annual_schedule(valuation: date, maturity: date) -> List[date]:
    """Return annual payment dates from valuation+1Y up to (and including) maturity."""
    dates: List[date] = []
    t = valuation
    while True:
        t = add_tenor(t, "1Y")
        if t >= maturity:
            dates.append(maturity)
            break
        dates.append(t)
    return dates


# ---------------------------------------------------------------------------
# Helper: fill missing annual tenors by linear interpolation of par rates
# ---------------------------------------------------------------------------

def _fill_annual_tenors(
    ois_quotes: Dict[str, float],
    swap_quotes: Dict[str, float],
    valuation: date,
) -> Dict[str, float]:
    """
    Return a combined dict of ALL integer-year tenors (1Y … max_Y) with
    par rates. Missing years are linearly interpolated from surrounding quotes.
    OIS 1Y quote takes priority over any swap 1Y quote.
    """
    # Merge: ois 1Y anchor + swap quotes
    all_quotes: Dict[str, float] = {}

    # Use 1Y OIS if present; otherwise fall back to any 1Y swap quote
    if "1Y" in ois_quotes:
        all_quotes["1Y"] = ois_quotes["1Y"]

    for tenor, rate in swap_quotes.items():
        all_quotes[tenor] = rate

    # Convert to year-fraction keys for easy arithmetic
    known_yr: Dict[float, float] = {}
    for tenor, rate in all_quotes.items():
        mat = add_tenor(valuation, tenor)
        yr = round((mat - valuation).days / 365.25)
        if yr > 0:
            known_yr[float(yr)] = rate

    if not known_yr:
        return {}

    max_yr = int(max(known_yr.keys()))
    sorted_yrs = sorted(known_yr.keys())

    result: Dict[str, float] = {}
    for y in range(1, max_yr + 1):
        t = float(y)
        if t in known_yr:
            result[f"{y}Y"] = known_yr[t]
        else:
            # Linear interpolation between surrounding known points
            lowers = [s for s in sorted_yrs if s < t]
            uppers = [s for s in sorted_yrs if s > t]
            if not lowers or not uppers:
                # Flat extrapolation at boundary
                boundary = sorted_yrs[0] if not lowers else sorted_yrs[-1]
                result[f"{y}Y"] = known_yr[boundary]
            else:
                t0, t1 = max(lowers), min(uppers)
                r0, r1 = known_yr[t0], known_yr[t1]
                result[f"{y}Y"] = r0 + (r1 - r0) * (t - t0) / (t1 - t0)

    return result


# ---------------------------------------------------------------------------
# Main bootstrapper
# ---------------------------------------------------------------------------

class USDSOFRCurve(IRCurve):
    """
    USD SOFR IRS Curve.

    Parameters
    ----------
    valuation_date : date
        Curve valuation / reference date.
    ois_quotes : dict
        Short-end SOFR OIS rates. Keys are tenor strings (e.g. '1M', '6M', '1Y').
        Values are rates as decimals (e.g. 0.0530 = 5.30%).
    swap_quotes : dict
        Par SOFR IRS fixed rates for tenors > 1Y.
        Keys are tenor strings (e.g. '2Y', '5Y', '10Y').
        Values are rates as decimals.
    """

    DAY_COUNT = "ACT/360"

    def __init__(
        self,
        valuation_date: date,
        ois_quotes: Dict[str, float],
        swap_quotes: Dict[str, float],
    ):
        super().__init__(valuation_date, name="USD_SOFR_IRS")
        self._ois_quotes = ois_quotes
        self._swap_quotes = swap_quotes
        self._bootstrap()

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        val = self.valuation_date

        pillar_times: List[float] = []
        pillar_dfs: List[float] = []

        # --- Step 1: Short end OIS (sub-1Y tenors) ---
        ois_sub1y = {
            k: v for k, v in self._ois_quotes.items()
            if (add_tenor(val, k) - val).days < 365
        }
        ois_items = sorted(
            ois_sub1y.items(),
            key=lambda kv: (add_tenor(val, kv[0]) - val).days,
        )

        for tenor, rate in ois_items:
            mat = add_tenor(val, tenor)
            tau = dcf(val, mat, self.DAY_COUNT)
            df = 1.0 / (1.0 + rate * tau)
            t = (mat - val).days / 365.0
            pillar_times.append(t)
            pillar_dfs.append(df)

        self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

        # --- Step 2: Fill all integer-year tenors & bootstrap in order ---
        annual_quotes = _fill_annual_tenors(self._ois_quotes, self._swap_quotes, val)

        for yr in range(1, max(int(k[:-1]) for k in annual_quotes) + 1):
            tenor = f"{yr}Y"
            if tenor not in annual_quotes:
                continue
            par_rate = annual_quotes[tenor]
            mat = add_tenor(val, tenor)
            schedule = _annual_schedule(val, mat)

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
                raise RuntimeError(
                    f"Non-positive DF at {tenor}: DF={df_N:.6f}. Check input rates."
                )

            pillar_times.append(t_N)
            pillar_dfs.append(df_N)
            self._set_pillars(pillar_times.copy(), pillar_dfs.copy())

    # ------------------------------------------------------------------
    # Convenience: par swap rate implied by the curve
    # ------------------------------------------------------------------

    def par_swap_rate(self, tenor: str) -> float:
        """Fair fixed rate for a SOFR IRS of given tenor (curve validation)."""
        val = self.valuation_date
        mat = add_tenor(val, tenor)
        schedule = _annual_schedule(val, mat)

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
