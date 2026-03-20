"""
Interpolation methods for interest rate curves.
"""
import numpy as np
from scipy.interpolate import interp1d


def linear_interp(x_known: np.ndarray, y_known: np.ndarray, x_query: np.ndarray) -> np.ndarray:
    """Linear interpolation with flat extrapolation at boundaries."""
    f = interp1d(x_known, y_known, kind="linear", bounds_error=False,
                 fill_value=(y_known[0], y_known[-1]))
    return f(x_query)


def log_linear_df(t_known: np.ndarray, df_known: np.ndarray, t_query: np.ndarray) -> np.ndarray:
    """
    Log-linear interpolation on discount factors:
      log(DF) is linearly interpolated -> equivalent to linear zero rates.
    """
    log_df = np.log(df_known)
    interp_log = linear_interp(t_known, log_df, t_query)
    return np.exp(interp_log)


def monotone_convex_df(
    t_known: np.ndarray,
    df_known: np.ndarray,
    t_query: np.ndarray,
) -> np.ndarray:
    """
    Monotone Convex interpolation on discount factors (Hagan & West, 2006).

    4가지 보장 속성:
      1. 순간 선도금리(instantaneous forward) 양수 – 필라 사이 음수 금리 발생 없음
      2. 선도금리 연속 – 필라 경계에서 점프(sawtooth) 없음
      3. 적분 정합성 – ∫g(t)dt = -ln(DF(T2)/DF(T1)) 정확히 보존
      4. 필라 정확 통과 – DF(t_i) = df_known[i] 수학적으로 보장

    Algorithm
    ---------
    Step 1. 각 구간 이산 선도금리:   f_i = -Δln(DF) / Δt
    Step 2. 필라 순간 선도금리 추정: g_i = 인접 구간 길이 가중 평균
    Step 3. 단조성 제약:             부호 전환 시 g_i = 0, 그 외 2*min(|f_i|,|f_{i+1}|) 클램핑
    Step 4. 구간 내 2차(quadratic) 보간:
            g(x) = g_i + (6f-4g_i-2g_{i+1})x + (3g_i+3g_{i+1}-6f)x²
            (x = 정규화 좌표, ∫_0^1 g dx = f_i 면적 보존)
    Step 5. ln DF(t) = ln DF(t_i) - h_i * ∫_0^x g dy 적분으로 DF 복원

    Parameters
    ----------
    t_known : array, shape (n,)
        필라 시간 (연도 단위), 반드시 t_known[0] = 0, 단조 증가.
    df_known : array, shape (n,)
        필라 할인인수, df_known[0] = 1.
    t_query : array-like
        보간할 시간 배열.

    Returns
    -------
    np.ndarray : 보간된 할인인수
    """
    t_known = np.asarray(t_known, dtype=float)
    df_known = np.asarray(df_known, dtype=float)
    t_query = np.atleast_1d(np.asarray(t_query, dtype=float))

    n = len(t_known)

    # ── 단일 필라: 상수 반환 ────────────────────────────────────────────
    if n <= 1:
        return np.ones_like(t_query)

    log_df = np.log(df_known)           # ln P(t_i)
    h = np.diff(t_known)                # 구간 길이 (n-1,)
    f = -np.diff(log_df) / h            # 이산 선도금리 (n-1,)

    # ── Step 2: 필라 순간 선도금리 g_i ────────────────────────────────
    g = np.empty(n)
    g[0]  = f[0]    # 좌측 경계: 평탄 외삽
    g[-1] = f[-1]   # 우측 경계: 평탄 외삽

    if n > 2:
        # 인접 구간 길이 가중 평균: 균일하지 않은 그리드 대응
        # g_i = (f_{i-1}·h_i + f_i·h_{i-1}) / (h_{i-1} + h_i)
        w = (f[:-1] * h[1:] + f[1:] * h[:-1]) / (h[:-1] + h[1:])

        # ── Step 3: 단조성 제약 ──────────────────────────────────────
        same_sign = f[:-1] * f[1:] > 0.0
        # 부호 동일: 인접 이산 선도금리의 2배를 상한으로 클램핑
        clamped = np.sign(f[:-1]) * np.minimum(
            np.minimum(np.abs(w), 2.0 * np.abs(f[:-1])),
            2.0 * np.abs(f[1:]),
        )
        # 부호 전환: g_i = 0 (단조성 유지)
        g[1:-1] = np.where(same_sign, clamped, 0.0)

    # ── Step 4-5: 벡터화 보간 ────────────────────────────────────────
    result = np.empty_like(t_query)

    below  = t_query <= t_known[0]
    above  = t_query >= t_known[-1]
    inside = ~below & ~above

    # 필라 좌측 외삽: DF 고정
    result[below] = df_known[0]

    # 필라 우측 외삽: 마지막 이산 선도금리로 평탄 연장
    if above.any():
        result[above] = df_known[-1] * np.exp(
            -f[-1] * (t_query[above] - t_known[-1])
        )

    # 구간 내 보간
    if inside.any():
        t_in = t_query[inside]

        # 구간 인덱스: t_in ∈ [t_known[seg], t_known[seg+1])
        seg = np.searchsorted(t_known, t_in, side="right") - 1
        seg = np.clip(seg, 0, n - 2)

        x   = (t_in - t_known[seg]) / h[seg]   # 정규화 좌표 ∈ [0,1]
        fi  = f[seg]
        gi  = g[seg]
        gi1 = g[seg + 1]

        # ∫_0^x g(y) dy (정규화 좌표)
        # = g_i·x + (3f-2g_i-g_{i+1})·x² + (g_i+g_{i+1}-2f)·x³
        integral = (
            gi * x
            + (3.0 * fi - 2.0 * gi - gi1) * x ** 2
            + (gi + gi1 - 2.0 * fi) * x ** 3
        )

        # ln DF(t) = ln DF(t_seg) - h_seg · integral
        result[inside] = np.exp(log_df[seg] - h[seg] * integral)

    return result
