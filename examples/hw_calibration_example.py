"""
Hull-White Calibration Example
===============================
KRW KTB 제로커브 기반으로 Hull-White 모델의:
  1. Curve Fitting 검증 (시장 DF vs 모델 DF)
  2. 스왑션 Normal Vol 기반 (κ, σ) 캘리브레이션
을 수행하는 예제.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
import numpy as np

from curves.krw_ktb_curve import KRWKTBCurve
from calibration.hw_calibrator import HWCalibrator


def main():
    # ──────────────────────────────────────────────────────────
    # 1. 시장 제로커브 구축 (KRW KTB)
    # ──────────────────────────────────────────────────────────
    val_date = date(2025, 3, 17)
    bond_quotes = {
        "1Y": 0.0270,
        "2Y": 0.0265,
        "3Y": 0.0268,
        "5Y": 0.0280,
        "10Y": 0.0300,
        "20Y": 0.0295,
        "30Y": 0.0290,
    }
    curve = KRWKTBCurve(
        valuation_date=val_date,
        bond_quotes=bond_quotes,
        short_rate_3m=0.0335,
        short_rate_6m=0.0290,
    )
    print(f"시장 커브 구축 완료: {curve}")
    print()

    # ──────────────────────────────────────────────────────────
    # 2. Curve Fitting 검증
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [1단계] Curve Fitting 검증")
    print("=" * 60)

    calibrator = HWCalibrator(curve, kappa=0.03, sigma=0.01)
    print(calibrator.summary())
    print()

    fit_df = calibrator.validate_curve_fit()
    print(fit_df.to_string())
    print()

    max_error = fit_df["Abs Error"].max()
    print(f"최대 Fitting 오차: {max_error:.2e}")
    if max_error < 1e-10:
        print("→ PASS: 모델 DF가 시장 DF를 정확히 재현합니다.")
    else:
        print("→ WARNING: Fitting 오차가 예상보다 큽니다.")
    print()

    # ──────────────────────────────────────────────────────────
    # 3. ZBO Put-Call Parity 검증
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [검증] ZBO Put-Call Parity")
    print("=" * 60)

    T0, T = 1.0, 5.0
    X = 0.85
    call = calibrator.zero_bond_option(T0, T, X, "call")
    put = calibrator.zero_bond_option(T0, T, X, "put")
    P_T = float(curve.discount_factor(np.array([T]))[0])
    P_T0 = float(curve.discount_factor(np.array([T0]))[0])
    parity_lhs = call - put
    parity_rhs = P_T - X * P_T0

    print(f"  Call({T0}Y, {T}Y, X={X}): {call:.8f}")
    print(f"  Put ({T0}Y, {T}Y, X={X}): {put:.8f}")
    print(f"  Call - Put  = {parity_lhs:.8f}")
    print(f"  P(T) - X·P(T0) = {parity_rhs:.8f}")
    print(f"  차이: {abs(parity_lhs - parity_rhs):.2e}")
    if abs(parity_lhs - parity_rhs) < 1e-10:
        print("→ PASS: Put-Call Parity 성립")
    else:
        print("→ WARNING: Put-Call Parity 불일치")
    print()

    # ──────────────────────────────────────────────────────────
    # 4. 스왑션 가격 예시 (캘리브레이션 전)
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [참고] 캘리브레이션 전 스왑션 가격/Vol")
    print("=" * 60)

    for T0_ex in [1.0, 5.0]:
        for tenor_ex in [1.0, 5.0]:
            price = calibrator.swaption_price(T0_ex, tenor_ex)
            nvol = calibrator.swaption_normal_vol(T0_ex, tenor_ex)
            nvol_bps = nvol * 10000 if not np.isnan(nvol) else float("nan")
            print(f"  {T0_ex:.0f}Y×{tenor_ex:.0f}Y ATM Payer: "
                  f"Price={price:.8f}, NormalVol={nvol_bps:.2f} bps")
    print()

    # ──────────────────────────────────────────────────────────
    # 5. (κ, σ) 캘리브레이션
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [2단계] (κ, σ) 캘리브레이션 (스왑션 Normal Vol)")
    print("=" * 60)

    result = calibrator.calibrate()

    print(f"\n최적화 결과:")
    print(f"  κ (kappa) = {result['kappa']:.6f}")
    print(f"  σ (sigma) = {result['sigma']:.6f}")
    print(f"  RMSE      = {result['rmse_bps']:.4f} bps")
    print(f"  수렴 여부  = {result['success']}")
    print(f"  메시지     = {result['message']}")
    print()

    print("캘리브레이션 상세 결과:")
    print(result["details"].to_string(index=False))
    print()

    # ──────────────────────────────────────────────────────────
    # 6. 캘리브레이션 후 Curve Fitting 재검증
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [검증] 캘리브레이션 후 Curve Fitting 재검증")
    print("=" * 60)

    fit_df2 = calibrator.validate_curve_fit()
    print(fit_df2.to_string())
    max_error2 = fit_df2["Abs Error"].max()
    print(f"\n최대 Fitting 오차 (캘리브레이션 후): {max_error2:.2e}")
    if max_error2 < 1e-10:
        print("→ PASS: 캘리브레이션 후에도 시장 DF 정확 재현 유지")
    else:
        print("→ WARNING: 캘리브레이션으로 인한 Fitting 오차 발생")

    print()
    print(calibrator.summary())


if __name__ == "__main__":
    main()
