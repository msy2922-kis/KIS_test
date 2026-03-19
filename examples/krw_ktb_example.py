"""
KRW KTB (국고채) Yield Curve – Usage Example
=============================================
Demonstrates how to build a KTB zero curve from market par yields
and query Zero Rate, Discount Factor, and Forward Rate.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from curves.krw_ktb_curve import KRWKTBCurve

# ---------------------------------------------------------------------------
# Market data (approximate KRW KTB quotes as of 2024-03-19)
# ---------------------------------------------------------------------------
valuation = date(2024, 3, 19)

short_rate_3m = 0.0355   # 3M Treasury bill (단리, simple interest)
short_rate_6m = 0.0350   # 6M Treasury bill (단리, simple interest)

bond_quotes = {
    "1Y":  0.0345,
    "2Y":  0.0335,
    "3Y":  0.0330,
    "5Y":  0.0335,
    "10Y": 0.0350,
    "20Y": 0.0360,
    "30Y": 0.0355,
    "50Y": 0.0345,
}

# ---------------------------------------------------------------------------
# Build curve
# ---------------------------------------------------------------------------
curve = KRWKTBCurve(
    valuation_date=valuation,
    bond_quotes=bond_quotes,
    short_rate_3m=short_rate_3m,
    short_rate_6m=short_rate_6m,
)

print(f"\n{'='*60}")
print(f"  {curve}")
print(f"{'='*60}")

# ---------------------------------------------------------------------------
# Curve summary
# ---------------------------------------------------------------------------
import numpy as np

tenors_yr = [3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50]
summary = curve.summary(tenors_yr)
print("\n[Curve Summary]")
print(summary.to_string())

# ---------------------------------------------------------------------------
# Spot queries
# ---------------------------------------------------------------------------
print("\n[Spot Queries]")
for t in [0.25, 1.0, 5.0, 10.0, 30.0]:
    zr  = curve.zero_rate(t)[0] * 100
    df  = curve.discount_factor(t)[0]
    fwd = curve.forward_rate(t, t + 0.25)[0] * 100
    print(f"  t={t:5.2f}Y  ZeroRate={zr:.4f}%  DF={df:.6f}  3M-Fwd={fwd:.4f}%")

# ---------------------------------------------------------------------------
# Validation: implied par yield vs input
# ---------------------------------------------------------------------------
print("\n[Validation – Implied Par Yield vs Input]")
print(f"  {'Tenor':<8} {'Input (%)':>10} {'Implied (%)':>12} {'Error (bps)':>12}")
print(f"  {'-'*46}")
for tenor, input_rate in bond_quotes.items():
    implied = curve.par_bond_yield(tenor)
    error_bps = (implied - input_rate) * 10_000
    print(f"  {tenor:<8} {input_rate*100:>10.4f} {implied*100:>12.4f} {error_bps:>12.4f}")
