"""
USD SOFR IRS Curve Example
===========================
Demonstrates bootstrapping a USD SOFR IRS curve from market quotes
and extracting zero rates, discount factors, and forward rates.

Sample market data as of 2024-03-19 (illustrative).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from curves.usd_sofr_curve import USDSOFRCurve

# ---------------------------------------------------------------------------
# 1. Market data input
#    OIS quotes  : SOFR OIS rates for short tenors (simple, Act/360)
#    Swap quotes : Par SOFR IRS fixed rates for standard tenors
# ---------------------------------------------------------------------------

VALUATION_DATE = date(2024, 3, 19)

OIS_QUOTES = {
    "1M":  0.0531,   # 5.31%
    "3M":  0.0533,   # 5.33%
    "6M":  0.0527,   # 5.27%
    "1Y":  0.0502,   # 5.02%
}

SWAP_QUOTES = {
    "2Y":  0.0468,   # 4.68%
    "3Y":  0.0449,   # 4.49%
    "5Y":  0.0437,   # 4.37%
    "7Y":  0.0438,   # 4.38%
    "10Y": 0.0440,   # 4.40%
    "15Y": 0.0445,   # 4.45%
    "20Y": 0.0445,   # 4.45%
    "30Y": 0.0435,   # 4.35%
}

# ---------------------------------------------------------------------------
# 2. Build curve
# ---------------------------------------------------------------------------

curve = USDSOFRCurve(
    valuation_date=VALUATION_DATE,
    ois_quotes=OIS_QUOTES,
    swap_quotes=SWAP_QUOTES,
)

print("=" * 60)
print(f"  {curve}")
print("=" * 60)

# ---------------------------------------------------------------------------
# 3. Print summary table
# ---------------------------------------------------------------------------

import numpy as np

tenors_yr = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
summary = curve.summary(tenors_yr)

print("\n[USD SOFR IRS Curve – Summary]\n")
print(summary.to_string())

# ---------------------------------------------------------------------------
# 4. Validate: implied par rates should match input quotes
# ---------------------------------------------------------------------------

print("\n[Validation – Implied Par Rates vs. Input]\n")
print(f"{'Tenor':<8} {'Input Rate':>12} {'Implied Rate':>13} {'Error (bps)':>12}")
print("-" * 48)

for tenor, input_rate in {**OIS_QUOTES, **SWAP_QUOTES}.items():
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
