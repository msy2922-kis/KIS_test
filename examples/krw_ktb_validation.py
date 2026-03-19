"""
KRW KTB Curve – 4-Property Validation
======================================
현재 구현(log-linear DF = piecewise-linear zero rate)이 다음 4가지 속성을
만족하는지 수치적으로 검증합니다.

1. Monotone Convex 보간 충족 여부
   - 순간 선도금리(instantaneous forward) 양수 보장 여부
   - 필라 경계에서의 선도금리 연속성 여부 (진정한 MC의 필수 조건)

2. Sawtooth 현상 발생 여부
   - 필라 경계에서 선도금리 점프 방향이 교번(교대)하는지 확인

3. 적분 정합성 (Area Preservation)
   - 각 구간 [t_k, t_{k+1}]에서 수치 적분한 선도금리 면적이
     -ln(DF(t_{k+1})/DF(t_k))와 일치하는지 확인

4. No-Arbitrage (입력값 역산)
   - 커브에서 역산한 Par Yield가 입력 수익률과 일치하는지 확인
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from scipy import integrate as sci_integrate
from datetime import date
from curves.krw_ktb_curve import KRWKTBCurve

# ─────────────────────────────────────────────────────────────────
# 시장 데이터
# ─────────────────────────────────────────────────────────────────
valuation = date(2024, 3, 19)

short_rate_3m = 0.0355
short_rate_6m = 0.0350

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

curve = KRWKTBCurve(
    valuation_date=valuation,
    bond_quotes=bond_quotes,
    short_rate_3m=short_rate_3m,
    short_rate_6m=short_rate_6m,
)

# 내부 필라 시간 (t=0 제외)
pillar_times = curve._times[1:]

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

results = {}

# =================================================================
# CHECK 1: Monotone Convex 충족 여부
# =================================================================
print("=" * 65)
print("CHECK 1: Monotone Convex 충족 여부")
print("=" * 65)

# 1-A) 순간 선도금리 양수 여부 (MC의 필수 조건)
dense_t = np.linspace(0.01, float(pillar_times[-1]) * 0.9999, 5000)
dt = 1e-5
inst_fwd = (
    np.log(curve.discount_factor(dense_t))
    - np.log(curve.discount_factor(dense_t + dt))
) / dt

min_fwd = inst_fwd.min()
neg_count = (inst_fwd < 0).sum()

print(f"\n  [1-A] 순간 선도금리 최솟값  : {min_fwd*100:.6f}%")
print(f"        음수 발생 횟수         : {neg_count} / {len(dense_t)}")
check_1a = PASS if neg_count == 0 else FAIL
print(f"        결과                   : {check_1a}")

# 1-B) 필라 경계에서의 선도금리 연속성
#   log-linear DF = 구간별 상수 순간 선도금리 → 경계에서 점프 발생
eps = 1e-6
jumps = []
for t in pillar_times[:-1]:
    f_left  = (np.log(curve.discount_factor(t - eps)) - np.log(curve.discount_factor(t - eps + dt))) / dt
    f_right = (np.log(curve.discount_factor(t + eps)) - np.log(curve.discount_factor(t + eps + dt))) / dt
    jump_bps = (f_right[0] - f_left[0]) * 10_000
    jumps.append((float(t), float(f_left[0]) * 100, float(f_right[0]) * 100, jump_bps))

max_abs_jump = max(abs(j[3]) for j in jumps)
print(f"\n  [1-B] 필라 경계 선도금리 최대 점프 : {max_abs_jump:.4f} bps")
print(f"        (log-linear DF는 구간별 상수 선도금리 → 경계 점프 내재)")
print(f"        → 진정한 Monotone Convex(Hagan-West) 보간법 ≠ 현재 구현")

has_continuity = max_abs_jump < 0.01  # practically zero jump
check_1b = PASS if has_continuity else WARN
print(f"        결과                               : {check_1b}")

results["1A_positive_forward"] = check_1a
results["1B_continuous_forward"] = check_1b

# =================================================================
# CHECK 2: Sawtooth 현상
# =================================================================
print("\n" + "=" * 65)
print("CHECK 2: Sawtooth 현상")
print("=" * 65)

# 각 필라 구간의 평균 순간 선도금리 계산 (구간별 상수)
seg_fwds = []
for i in range(len(pillar_times) - 1):
    t_mid = (float(pillar_times[i]) + float(pillar_times[i+1])) / 2
    f = (np.log(curve.discount_factor(t_mid)) - np.log(curve.discount_factor(t_mid + dt))) / dt
    seg_fwds.append(float(f[0]) * 100)

# 방향 변화 횟수: 연속된 구간에서 선도금리가 교번하는지
direction_changes = 0
alternating_runs = 0
for i in range(1, len(seg_fwds) - 1):
    prev_diff = seg_fwds[i] - seg_fwds[i-1]
    next_diff = seg_fwds[i+1] - seg_fwds[i]
    if prev_diff * next_diff < 0:
        direction_changes += 1

sawtooth_ratio = direction_changes / max(len(seg_fwds) - 2, 1)

print(f"\n  구간 수              : {len(seg_fwds)}")
print(f"  방향 전환 횟수       : {direction_changes}")
print(f"  Sawtooth 비율        : {sawtooth_ratio:.1%}  (< 30% → 경미)")
print(f"  선도금리 범위        : [{min(seg_fwds):.4f}%, {max(seg_fwds):.4f}%]")
print(f"  선도금리 표준편차    : {np.std(seg_fwds):.4f}%")

# Sawtooth 심각도 판단: 방향 전환 비율 + 최대 인접 구간 점프 크기
adjacent_jumps = [abs(seg_fwds[i+1] - seg_fwds[i]) for i in range(len(seg_fwds)-1)]
max_adj_jump = max(adjacent_jumps)
print(f"  인접 구간 최대 점프  : {max_adj_jump:.4f}%  ({max_adj_jump*100:.2f} bps)")

check_2 = PASS if sawtooth_ratio < 0.30 and max_adj_jump < 0.50 else WARN
print(f"\n  결과: {check_2}")
results["2_sawtooth"] = check_2

# 필라별 상세 (처음 10개)
print(f"\n  {'구간':<10} {'선도금리(%)':>12} {'인접 점프(bps)':>15}")
print(f"  {'-'*40}")
for i, f in enumerate(seg_fwds[:10]):
    jump_str = f"{adjacent_jumps[i]*100:+.2f}" if i < len(adjacent_jumps) else "   -"
    t_lo = float(pillar_times[i])
    t_hi = float(pillar_times[i+1])
    print(f"  [{t_lo:.2f}Y-{t_hi:.2f}Y]{'':<2} {f:>12.4f} {jump_str:>15}")

# =================================================================
# CHECK 3: 적분 정합성 (Area Preservation)
# =================================================================
print("\n" + "=" * 65)
print("CHECK 3: 적분 정합성 (Area Preservation)")
print("=" * 65)

print(f"\n  이론값: -ln(DF(t2)/DF(t1)) = 구간 [t1,t2]의 선도금리 면적")
print(f"  검증  : scipy 수치 적분 vs log(DF) 차이 비교\n")

max_area_err = 0.0
print(f"  {'구간':<18} {'이론 면적':>12} {'수치 면적':>12} {'오차':>10}")
print(f"  {'-'*56}")

area_errors = []
for i in range(min(len(pillar_times) - 1, 12)):
    t1 = float(pillar_times[i])
    t2 = float(pillar_times[i+1])

    # 이론값: -ln(DF(t2)/DF(t1))
    df1 = curve.discount_factor(t1)[0]
    df2 = curve.discount_factor(t2)[0]
    theoretical = -np.log(df2 / df1)

    # 수치 적분: ∫f(t)dt
    def inst_fwd_func(t):
        return (np.log(curve.discount_factor(np.array([t]))[0])
                - np.log(curve.discount_factor(np.array([t + dt]))[0])) / dt

    numerical, _ = sci_integrate.quad(inst_fwd_func, t1, t2, limit=200)
    err = abs(numerical - theoretical)
    area_errors.append(err)
    max_area_err = max(max_area_err, err)

    print(f"  [{t1:.4f}Y, {t2:.4f}Y]  {theoretical:>12.8f} {numerical:>12.8f} {err:>10.2e}")

check_3 = PASS if max_area_err < 1e-6 else FAIL
print(f"\n  최대 적분 오차: {max_area_err:.2e}")
print(f"  결과: {check_3}")
results["3_area_preservation"] = check_3

# =================================================================
# CHECK 4: No-Arbitrage (입력값 역산)
# =================================================================
print("\n" + "=" * 65)
print("CHECK 4: No-Arbitrage – 입력 Par Yield 역산")
print("=" * 65)

print(f"\n  {'Tenor':<8} {'Input (%)':>10} {'Implied (%)':>12} {'Error (bps)':>12} {'판정':>8}")
print(f"  {'-'*54}")

max_arb_err = 0.0
arb_results = []
for tenor, input_rate in bond_quotes.items():
    implied = curve.par_bond_yield(tenor)
    err_bps = abs(implied - input_rate) * 10_000
    max_arb_err = max(max_arb_err, err_bps)
    flag = "✅" if err_bps < 0.5 else "❌"
    arb_results.append(err_bps)
    print(f"  {tenor:<8} {input_rate*100:>10.4f} {implied*100:>12.4f} {(implied-input_rate)*10000:>+12.6f} {flag:>8}")

check_4 = PASS if max_arb_err < 0.5 else FAIL
print(f"\n  최대 역산 오차: {max_arb_err:.6f} bps")
print(f"  결과: {check_4}")
results["4_no_arbitrage"] = check_4

# =================================================================
# 최종 요약
# =================================================================
print("\n" + "=" * 65)
print("최종 검증 요약")
print("=" * 65)
print(f"""
  ┌─────────────────────────────────────────────────────────┐
  │  검증 항목                              결과             │
  ├─────────────────────────────────────────────────────────┤
  │  1-A. 순간 선도금리 양수 (MC 필수조건)  {results['1A_positive_forward']:<22}│
  │  1-B. 선도금리 연속성 (MC 완전 조건)    {results['1B_continuous_forward']:<22}│
  │  2.   Sawtooth 현상 억제               {results['2_sawtooth']:<22}│
  │  3.   적분 정합성 (Area Preservation)  {results['3_area_preservation']:<22}│
  │  4.   No-Arbitrage (입력값 역산)       {results['4_no_arbitrage']:<22}│
  └─────────────────────────────────────────────────────────┘

  ◆ 구현 방식: Log-Linear DF (= 구간별 선형 Zero Rate)
    → 구간 내 순간 선도금리: 상수 (piecewise constant)
    → 선도금리 필라 경계 불연속 내재 (1-B ⚠️ 원인)
    → 적분 정합성·No-Arbitrage는 수학적으로 보장됨
    → 진정한 Hagan-West Monotone Convex와는 상이한 방법론
       (MC가 필요하면 utils/interpolation.py 교체 필요)
""")
