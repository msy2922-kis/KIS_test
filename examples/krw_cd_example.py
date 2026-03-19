"""
KRW CD IRS Curve Example
=========================
Demonstrates bootstrapping a KRW CD IRS curve from market quotes
and extracting zero rates, discount factors, and forward rates.

Sample market data (illustrative).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from curves.krw_cd_curve import KRWCDCurve

# ---------------------------------------------------------------------------
# 1. Market data input
#    cd_rate    : 91-day CD rate (Act/365, simple interest)
#    swap_quotes: Par CD IRS fixed rates for standard tenors (quarterly fixed)
# ---------------------------------------------------------------------------

VALUATION_DATE = date(2024, 3, 19)

CD_RATE_91D = 0.0368   # 3.68% (91-day CD rate)

SWAP_QUOTES = {
    "6M":  0.0362,   # 3.62%
    "1Y":  0.0353,   # 3.53%
    "2Y":  0.0340,   # 3.40%
    "3Y":  0.0335,   # 3.35%
    "5Y":  0.0337,   # 3.37%
    "7Y":  0.0342,   # 3.42%
    "10Y": 0.0350,   # 3.50%
    "20Y": 0.0360,   # 3.60%
    "30Y": 0.0355,   # 3.55%
}

# ---------------------------------------------------------------------------
# 2. Build curve
# ---------------------------------------------------------------------------

curve = KRWCDCurve(
    valuation_date=VALUATION_DATE,
    cd_rate=CD_RATE_91D,
    swap_quotes=SWAP_QUOTES,
)

print("=" * 60)
print(f"  {curve}")
print("=" * 60)

# ---------------------------------------------------------------------------
# 3. Print summary table
# ---------------------------------------------------------------------------

import numpy as np

tenors_yr = [3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
summary = curve.summary(tenors_yr)

print("\n[KRW CD IRS Curve – Summary]\n")
print(summary.to_string())

# ---------------------------------------------------------------------------
# 4. Validate: implied par rates should match input quotes
# ---------------------------------------------------------------------------

print("\n[Validation – Implied Par Rates vs. Input]\n")
print(f"{'Tenor':<8} {'Input Rate':>12} {'Implied Rate':>13} {'Error (bps)':>12}")
print("-" * 48)

for tenor, input_rate in SWAP_QUOTES.items():
    implied = curve.par_swap_rate(tenor)
    error_bps = (implied - input_rate) * 10_000
    print(f"{tenor:<8} {input_rate*100:>11.4f}% {implied*100:>12.4f}% {error_bps:>11.4f}")

# ---------------------------------------------------------------------------
# 5. Query specific tenors
# ---------------------------------------------------------------------------

print("\n[Spot Queries]\n")
for t, label in [(0.25, "3M"), (1.0, "1Y"), (5.0, "5Y"), (10.0, "10Y")]:
    z  = curve.zero_rate(t)[0]
    df = curve.discount_factor(t)[0]
    f  = curve.forward_rate(t, t + 0.25)[0]  # 3M forward
    print(f"  {label:>4}  Zero={z*100:.4f}%  DF={df:.6f}  3M Fwd={f*100:.4f}%")
