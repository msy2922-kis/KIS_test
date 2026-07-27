"""
Hull-White 1-Factor Curve Fitting & Calibration
=================================================
시장 제로커브에 대한 Curve Fitting 검증과
스왑션 Normal Vol 기반 (κ, σ) 캘리브레이션을 수행한다.

주요 기능:
  1. Curve Fitting 검증 – HW 모델이 시장 DF를 정확히 재현하는지 확인
  2. Zero-Bond Option 해석적 가격 산출
  3. Swaption 가격 산출 (Jamshidian 분해)
  4. Caplet / Cap 가격 산출 (추후 확장용)
  5. (κ, σ) 캘리브레이션 – 스왑션 Normal Vol 기준
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize, brentq
from scipy.stats import norm

from curves.base_curve import IRCurve
from short_rate_models import HullWhiteModel


# ─────────────────────────────────────────────────────────────────────────────
# 가정 시장 데이터 (추후 실제 시장 데이터로 교체)
# ─────────────────────────────────────────────────────────────────────────────

# 스왑션 Normal Vol (소수, 예: 0.0045 = 45 bps)
_SAMPLE_SWAPTION_VOLS = [
    {"type": "swaption", "expiry": 1.0, "tenor": 1.0, "strike": "atm", "market_vol": 0.0045},
    {"type": "swaption", "expiry": 1.0, "tenor": 5.0, "strike": "atm", "market_vol": 0.0055},
    {"type": "swaption", "expiry": 5.0, "tenor": 5.0, "strike": "atm", "market_vol": 0.0050},
    {"type": "swaption", "expiry": 5.0, "tenor": 10.0, "strike": "atm", "market_vol": 0.0048},
    {"type": "swaption", "expiry": 10.0, "tenor": 10.0, "strike": "atm", "market_vol": 0.0046},
]


class HWCalibrator:
    """
    Hull-White 1-Factor 모델 Curve Fitting 및 Calibration.

    1단계: 시장 제로커브 Fitting 검증 – θ(t)가 자동으로 결정되어
           모델 할인인수(DF)가 시장 DF와 정확히 일치하는지 확인.
    2단계: 스왑션 Normal Vol에 대한 (κ, σ) 캘리브레이션.

    Parameters
    ----------
    curve : IRCurve
        부트스트랩된 시장 제로커브 (KRWKTBCurve, KRWCDCurve 등).
    kappa : float
        초기 mean-reversion 속도 (기본 0.03).
    sigma : float
        초기 변동성 (기본 0.01).
    """

    def __init__(
        self,
        curve: IRCurve,
        kappa: float = 0.03,
        sigma: float = 0.01,
    ):
        self.curve = curve
        self.kappa = kappa
        self.sigma = sigma
        # r0 를 모델의 순간선도금리 f^M(0,0) 과 일치시켜야
        # P_HW(0,T) = P^M(0,T) 가 수치적으로도 정확히 성립한다.
        # _make_fwd_from_ir_curve 에서 t=0 일 때 t_safe=1e-6 사용하므로 동일하게 맞춤.
        self.r0 = float(
            curve.forward_rate(
                np.array([1e-6]), np.array([1e-6 + 1e-5]), compounding="continuous"
            )[0]
        )
        self._build_model()

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _build_model(self) -> None:
        """현재 (κ, σ)로 HullWhiteModel 재생성."""
        self._model = HullWhiteModel(
            kappa=self.kappa,
            sigma=self.sigma,
            r0=self.r0,
            initial_curve=self.curve,
        )

    def _P0(self, t: float) -> float:
        """시장 할인인수 P^M(0, t)."""
        if t <= 0.0:
            return 1.0
        return float(self.curve.discount_factor(np.array([t]))[0])

    def _f0(self, t: float) -> float:
        """시장 순간선도금리 f^M(0, t)."""
        eps = 1e-5
        t_safe = max(t, eps)
        return float(
            self.curve.forward_rate(
                np.array([t_safe]), np.array([t_safe + eps]), compounding="continuous"
            )[0]
        )

    # ------------------------------------------------------------------
    # Curve Fitting 검증
    # ------------------------------------------------------------------

    def validate_curve_fit(
        self,
        tenors: list[float] | None = None,
    ) -> pd.DataFrame:
        """
        HW 모델의 해석적 채권 가격 P(0, T) vs 시장 DF 비교.

        Hull-White θ(t) 결정에 의해 P_HW(0,T) = P^M(0,T)이 이론적으로
        보장되므로, 수치 오차가 1e-10 이하인지 검증한다.

        Parameters
        ----------
        tenors : list[float], optional
            검증할 만기 배열 (연도). 미지정 시 0.25Y ~ 30Y 기본 그리드 사용.

        Returns
        -------
        pd.DataFrame
            각 만기별 시장 DF, 모델 DF, 절대 오차.
        """
        if tenors is None:
            tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]

        rows = []
        for T in tenors:
            df_market = self._P0(T)
            # HW 해석적 P(0, T) : t=0 에서 r=r0
            df_model = float(self._model.bond_price_analytical(self.r0, 0.0, T))
            rows.append({
                "Tenor (Y)": T,
                "Market DF": df_market,
                "Model DF": df_model,
                "Abs Error": abs(df_model - df_market),
            })

        df = pd.DataFrame(rows).set_index("Tenor (Y)")
        return df

    # ------------------------------------------------------------------
    # Zero-Bond Option (ZBO) 해석적 가격
    # ------------------------------------------------------------------

    def _B(self, t: float, T: float) -> float:
        """B(t, T) = (1 - e^{-κ(T-t)}) / κ"""
        tau = T - t
        return (1.0 - np.exp(-self.kappa * tau)) / self.kappa

    def _sigma_p(self, T0: float, T: float) -> float:
        """
        ZBO 변동성 (Brigo & Mercurio eq. 3.10):
        σ_p = (σ/κ)(1 - e^{-κ(T-T0)}) √((1 - e^{-2κT0}) / (2κ))
        """
        return (
            self.sigma
            / self.kappa
            * (1.0 - np.exp(-self.kappa * (T - T0)))
            * np.sqrt((1.0 - np.exp(-2.0 * self.kappa * T0)) / (2.0 * self.kappa))
        )

    def zero_bond_option(
        self,
        T0: float,
        T: float,
        X: float,
        option_type: str = "call",
    ) -> float:
        """
        Hull-White 해석적 Zero-Bond Option 가격.

        Call: P(0,T) N(h + σ_p) - X P(0,T0) N(h)
        Put:  X P(0,T0) N(-h) - P(0,T) N(-h - σ_p)

        Parameters
        ----------
        T0 : float
            옵션 만기 (year-fraction).
        T : float
            기초 채권 만기 (T > T0).
        X : float
            행사가격.
        option_type : str
            "call" 또는 "put".
        """
        P_T = self._P0(T)
        P_T0 = self._P0(T0)
        sp = self._sigma_p(T0, T)

        if sp < 1e-15:
            # 만기가 거의 같으면 내재 가치 반환
            if option_type == "call":
                return max(P_T - X * P_T0, 0.0)
            else:
                return max(X * P_T0 - P_T, 0.0)

        h = (1.0 / sp) * np.log(P_T / (P_T0 * X)) + sp / 2.0

        if option_type == "call":
            return P_T * norm.cdf(h + sp) - X * P_T0 * norm.cdf(h)
        else:
            return X * P_T0 * norm.cdf(-h) - P_T * norm.cdf(-h - sp)

    # ------------------------------------------------------------------
    # Caplet / Cap (추후 확장용, 프레임워크 구현)
    # ------------------------------------------------------------------

    def caplet_price(self, T_start: float, T_end: float, K: float) -> float:
        """
        Caplet 가격 = (1 + K·τ) × Put on ZCB.

        Caplet은 [T_start, T_end] 구간에 대한 Cap의 개별 구성 요소.
        Cap rate K에 대해, Caplet = (1+K·τ) × ZBO_put(T_start, T_end, X)
        여기서 X = 1 / (1 + K·τ).

        Parameters
        ----------
        T_start : float
            Caplet 시작 (= 옵션 만기).
        T_end : float
            Caplet 종료 (= 기초 채권 만기).
        K : float
            Cap strike rate.
        """
        tau = T_end - T_start
        X = 1.0 / (1.0 + K * tau)
        return (1.0 + K * tau) * self.zero_bond_option(T_start, T_end, X, option_type="put")

    def cap_price(self, cap_maturity: float, K: float, freq: float = 0.25) -> float:
        """
        Cap 가격 = Σ caplets.

        Parameters
        ----------
        cap_maturity : float
            Cap 전체 만기 (year-fraction).
        K : float
            Cap strike rate.
        freq : float
            지급 주기 (기본 0.25 = 분기).
        """
        n = max(1, int(round(cap_maturity / freq)))
        price = 0.0
        for i in range(1, n + 1):
            T_start = i * freq
            T_end = (i + 1) * freq
            if T_end > cap_maturity + freq + 1e-10:
                break
            price += self.caplet_price(T_start, T_end, K)
        return price

    def cap_black_vol(self, cap_maturity: float, K: float, freq: float = 0.25) -> float:
        """
        Cap 가격에서 Black (lognormal) implied vol 역산.

        Parameters
        ----------
        cap_maturity : float
            Cap 전체 만기.
        K : float
            Cap strike rate.
        freq : float
            지급 주기.
        """
        target = self.cap_price(cap_maturity, K, freq)
        if target < 1e-15:
            return 0.0

        def _cap_black_price(vol: float) -> float:
            """Black 공식으로 Cap 가격 계산."""
            n = max(1, int(round(cap_maturity / freq)))
            price = 0.0
            for i in range(1, n + 1):
                T_start = i * freq
                T_end = (i + 1) * freq
                if T_end > cap_maturity + freq + 1e-10:
                    break
                tau = T_end - T_start
                df_end = self._P0(T_end)
                fwd = (self._P0(T_start) / df_end - 1.0) / tau
                if fwd <= 0 or K <= 0:
                    continue
                d1 = (np.log(fwd / K) + 0.5 * vol ** 2 * T_start) / (vol * np.sqrt(T_start))
                d2 = d1 - vol * np.sqrt(T_start)
                price += tau * df_end * (fwd * norm.cdf(d1) - K * norm.cdf(d2))
            return price

        try:
            iv = brentq(lambda v: _cap_black_price(v) - target, 1e-6, 5.0, xtol=1e-8)
        except ValueError:
            iv = np.nan
        return iv

    # ------------------------------------------------------------------
    # Swaption 가격 (Jamshidian 분해)
    # ------------------------------------------------------------------

    def _par_swap_rate_from_curve(self, T0: float, swap_tenor: float, freq: float) -> float:
        """커브로부터 forward par swap rate 산출."""
        n = max(1, int(round(swap_tenor / freq)))
        annuity = 0.0
        for i in range(1, n + 1):
            T_i = T0 + i * freq
            annuity += freq * self._P0(T_i)
        P_start = self._P0(T0)
        P_end = self._P0(T0 + swap_tenor)
        if annuity < 1e-15:
            return 0.0
        return (P_start - P_end) / annuity

    def _find_r_star(
        self,
        T0: float,
        payment_times: list[float],
        cash_flows: list[float],
    ) -> float:
        """
        Jamshidian r* 탐색:
        Σ c_i · P_HW(T0, T_i; r*) = P_HW(T0, T0; r*) = 1  은 아니고,
        정확히는: Σ c_i · P(T0, T_i; r*) = 1  (par 조건)

        여기서 P(T0, T_i; r*) = exp(A(T0,T_i) - B(T0,T_i)·r*)

        Parameters
        ----------
        T0 : float
            스왑션 만기.
        payment_times : list[float]
            스왑 지급일 [T1, T2, ..., Tn].
        cash_flows : list[float]
            스왑 현금흐름 [c1, c2, ..., cn] (마지막에 원금 1 포함).
        """
        def objective(r: float) -> float:
            total = 0.0
            for T_i, c_i in zip(payment_times, cash_flows):
                total += c_i * float(self._model.bond_price_analytical(r, T0, T_i))
            return total - 1.0

        try:
            r_star = brentq(objective, -0.5, 0.5, xtol=1e-12)
        except ValueError:
            r_star = brentq(objective, -2.0, 2.0, xtol=1e-12)
        return r_star

    def swaption_price(
        self,
        T0: float,
        swap_tenor: float,
        K: float | None = None,
        freq: float = 0.5,
        option_type: str = "payer",
    ) -> float:
        """
        European swaption 해석적 가격 (Jamshidian's trick).

        Payer swaption: 고정금리 K를 지급하는 스왑에 대한 옵션.

        Parameters
        ----------
        T0 : float
            스왑션 만기 (= 스왑 시작일).
        swap_tenor : float
            스왑 잔존만기 (year-fraction).
        K : float or None
            스왑 고정금리 (행사가). None이면 ATM (forward par swap rate).
        freq : float
            스왑 고정금리 지급 주기 (기본 0.5 = 반기).
        option_type : str
            "payer" 또는 "receiver".
        """
        if K is None:
            K = self._par_swap_rate_from_curve(T0, swap_tenor, freq)

        # 스왑 지급 스케줄
        n = max(1, int(round(swap_tenor / freq)))
        payment_times = [T0 + (i + 1) * freq for i in range(n)]
        # 현금흐름: 쿠폰 + 마지막에 원금
        cash_flows = [K * freq] * n
        cash_flows[-1] += 1.0  # 원금 상환

        # r* 탐색
        r_star = self._find_r_star(T0, payment_times, cash_flows)

        # 각 지급일에 대한 strike price X_i = P(T0, T_i; r*)
        X_i = [float(self._model.bond_price_analytical(r_star, T0, T_i)) for T_i in payment_times]

        # Jamshidian 분해: swaption = Σ c_i × ZBO
        total = 0.0
        if option_type == "payer":
            # Payer swaption = sum of put options on zero bonds
            for c_i, T_i, xi in zip(cash_flows, payment_times, X_i):
                total += c_i * self.zero_bond_option(T0, T_i, xi, option_type="put")
        else:
            # Receiver swaption = sum of call options on zero bonds
            for c_i, T_i, xi in zip(cash_flows, payment_times, X_i):
                total += c_i * self.zero_bond_option(T0, T_i, xi, option_type="call")

        return total

    def swaption_normal_vol(
        self,
        T0: float,
        swap_tenor: float,
        K: float | None = None,
        freq: float = 0.5,
    ) -> float:
        """
        Swaption 가격에서 Normal (Bachelier) implied vol 역산.

        Bachelier 공식:
            Payer = Annuity × [(S-K)N(d) + σ_N√T · n(d)]
            d = (S - K) / (σ_N √T)

        ATM (S=K) 일 때:
            Payer = Annuity × σ_N × √(T/(2π))

        Parameters
        ----------
        T0 : float
            스왑션 만기.
        swap_tenor : float
            스왑 잔존만기.
        K : float or None
            스왑 고정금리. None이면 ATM.
        freq : float
            스왑 지급 주기.
        """
        if K is None:
            K = self._par_swap_rate_from_curve(T0, swap_tenor, freq)

        target = self.swaption_price(T0, swap_tenor, K, freq, option_type="payer")
        if target < 1e-18:
            return 0.0

        # Annuity 계산
        n = max(1, int(round(swap_tenor / freq)))
        annuity = sum(freq * self._P0(T0 + (i + 1) * freq) for i in range(n))
        S = self._par_swap_rate_from_curve(T0, swap_tenor, freq)

        def bachelier_price(sigma_n: float) -> float:
            """Bachelier (Normal) swaption 가격."""
            if sigma_n < 1e-15:
                return annuity * max(S - K, 0.0)
            sqrt_T = np.sqrt(T0)
            d = (S - K) / (sigma_n * sqrt_T) if sqrt_T > 1e-10 else 0.0
            return annuity * (
                (S - K) * norm.cdf(d) + sigma_n * sqrt_T * norm.pdf(d)
            )

        try:
            iv = brentq(lambda v: bachelier_price(v) - target, 1e-8, 0.1, xtol=1e-10)
        except ValueError:
            iv = np.nan
        return iv

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def calibrate(
        self,
        market_instruments: list[dict] | None = None,
        x0: tuple[float, float] = (0.03, 0.01),
        bounds: tuple[tuple[float, float], ...] = ((1e-4, 2.0), (1e-4, 0.10)),
    ) -> dict:
        """
        시장 스왑션 Normal Vol에 (κ, σ) 최적화.

        Parameters
        ----------
        market_instruments : list[dict] or None
            캘리브레이션 대상. None이면 sample_market_data() 사용.
            각 dict: {"type": "swaption", "expiry": T0, "tenor": swap_tenor,
                      "strike": K or "atm", "market_vol": normal_vol}
        x0 : tuple
            초기값 (κ₀, σ₀).
        bounds : tuple
            (κ, σ) 탐색 범위.

        Returns
        -------
        dict
            {"kappa": κ*, "sigma": σ*, "rmse": RMSE, "details": DataFrame}
        """
        if market_instruments is None:
            market_instruments = self.sample_market_data()

        # 스왑션만 필터링
        swaptions = [m for m in market_instruments if m["type"] == "swaption"]

        def objective(params: np.ndarray) -> float:
            kappa, sigma = params
            self.kappa = kappa
            self.sigma = sigma
            self._build_model()

            sse = 0.0
            for inst in swaptions:
                T0 = inst["expiry"]
                tenor = inst["tenor"]
                K = inst.get("strike")
                if K == "atm" or K is None:
                    K = None  # swaption_normal_vol 내부에서 ATM 처리
                market_vol = inst["market_vol"]
                try:
                    model_vol = self.swaption_normal_vol(T0, tenor, K)
                    if np.isnan(model_vol):
                        sse += 1.0  # penalty
                    else:
                        sse += (model_vol - market_vol) ** 2
                except Exception:
                    sse += 1.0  # penalty for failed pricing
            return sse

        result = minimize(
            objective,
            x0=np.array(x0),
            method="L-BFGS-B",
            bounds=bounds,
            options={"ftol": 1e-14, "gtol": 1e-10, "maxiter": 500},
        )

        # 최적 파라미터 적용
        self.kappa = result.x[0]
        self.sigma = result.x[1]
        self._build_model()

        # 결과 상세
        details = []
        for inst in swaptions:
            T0 = inst["expiry"]
            tenor = inst["tenor"]
            K = inst.get("strike")
            if K == "atm" or K is None:
                K = None
            market_vol = inst["market_vol"]
            try:
                model_vol = self.swaption_normal_vol(T0, tenor, K)
            except Exception:
                model_vol = np.nan
            details.append({
                "Expiry": T0,
                "Tenor": tenor,
                "Market Vol (bps)": market_vol * 10000,
                "Model Vol (bps)": model_vol * 10000 if not np.isnan(model_vol) else np.nan,
                "Error (bps)": (model_vol - market_vol) * 10000 if not np.isnan(model_vol) else np.nan,
            })

        details_df = pd.DataFrame(details)
        model_vols = details_df["Model Vol (bps)"].dropna().values
        market_vols = details_df["Market Vol (bps)"].dropna().values
        rmse = np.sqrt(np.mean((model_vols - market_vols) ** 2)) if len(model_vols) > 0 else np.nan

        return {
            "kappa": self.kappa,
            "sigma": self.sigma,
            "rmse_bps": rmse,
            "success": result.success,
            "message": result.message,
            "details": details_df,
        }

    # ------------------------------------------------------------------
    # 가정 시장 데이터
    # ------------------------------------------------------------------

    @staticmethod
    def sample_market_data() -> list[dict]:
        """
        테스트용 가정 스왑션 Normal Vol 데이터 반환.

        실제 시장 데이터가 준비되면 이 메서드를 교체하거나,
        calibrate()에 직접 데이터를 전달하면 된다.
        """
        return list(_SAMPLE_SWAPTION_VOLS)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """현재 캘리브레이터 상태 요약."""
        return (
            f"HWCalibrator\n"
            f"  Curve    : {self.curve}\n"
            f"  κ (kappa): {self.kappa:.6f}\n"
            f"  σ (sigma): {self.sigma:.6f}\n"
            f"  r₀       : {self.r0:.6f} ({self.r0*100:.4f}%)"
        )

    def __repr__(self) -> str:
        return f"<HWCalibrator κ={self.kappa:.4f} σ={self.sigma:.4f} | {self.curve}>"
