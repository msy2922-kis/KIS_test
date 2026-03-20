"""
Base class for bootstrapped interest rate curves.
Stores zero rates and discount factors on a time grid,
and provides query methods for any tenor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import date
from typing import List, Tuple

from utils.interpolation import monotone_convex_df


class IRCurve:
    """
    Generic bootstrapped IR curve.

    Internally stores:
        _times  : year-fractions from valuation date (sorted)
        _dfs    : discount factors P(0, t)

    Zero rates and forward rates are derived on demand.
    """

    def __init__(self, valuation_date: date, name: str = "IRCurve"):
        self.valuation_date = valuation_date
        self.name = name
        self._times: np.ndarray = np.array([0.0])
        self._dfs: np.ndarray = np.array([1.0])

    # ------------------------------------------------------------------
    # Internal builders (called by subclass bootstrappers)
    # ------------------------------------------------------------------

    def _set_pillars(self, times: List[float], dfs: List[float]) -> None:
        """Store bootstrapped pillar times and discount factors."""
        t = np.array([0.0] + list(times))
        d = np.array([1.0] + list(dfs))
        # ensure sorted
        order = np.argsort(t)
        self._times = t[order]
        self._dfs = d[order]

    def _densify(self, step: float = 0.25) -> None:
        """
        부트스트랩 완료 후 0.25Y 간격 가상 노드를 추가한다.

        동작 원리
        ---------
        1. 현재 MC 커브(시장 필라 기반)를 `step` 간격 그리드에서 평가
        2. 기존 시장 필라 시간과 가상 노드 시간을 병합
           - 시장 필라에서 `tol` 이내인 가상 노드는 중복 방지를 위해 생략
        3. 병합된 고밀도 그리드의 DF 를 저장
           → 시장 필라 DF 는 정확히 보존 (MC exact-pass-through 특성)
           → No-Arbitrage / Area Preservation / Monotone Convex 모두 유지

        Parameters
        ----------
        step : float
            가상 노드 간격 (연도 단위, 기본 0.25 = 분기).
        """
        tol = step * 0.02          # ≈ 1.8 일 (step=0.25 기준); 실제 날짜 단수 흡수
        t_max = self._times[-1]

        # step 간격 가상 노드 (floating-point 누적 오차 방지를 위해 round)
        t_virtual = np.round(np.arange(0.0, t_max + step * 0.5, step), 10)

        # 시장 필라 목록 (원본)
        t_market = list(self._times)

        # 시장 필라와 겹치지 않는 가상 노드만 추가
        t_extra = [
            tv for tv in t_virtual
            if all(abs(tv - tm) > tol for tm in t_market)
        ]

        t_combined = np.sort(np.array(t_market + t_extra))

        # 현재 MC 커브로 가상 노드 DF 평가 (시장 필라에서는 정확히 원값 반환)
        df_combined = monotone_convex_df(self._times, self._dfs, t_combined)

        self._times = t_combined
        self._dfs   = df_combined

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def discount_factor(self, t: float | np.ndarray) -> np.ndarray:
        """
        Interpolated discount factor P(0, t).
        t: year-fraction(s) from valuation date.
        """
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return monotone_convex_df(self._times, self._dfs, t)

    def zero_rate(self, t: float | np.ndarray, compounding: str = "continuous") -> np.ndarray:
        """
        Zero rate at maturity t (year-fraction).

        compounding:
            'continuous' : r = -ln(DF) / t
            'simple'     : r = (1/DF - 1) / t
            'annual'     : r = DF^(-1/t) - 1
        """
        t = np.atleast_1d(np.asarray(t, dtype=float))
        df = self.discount_factor(t)

        with np.errstate(divide="ignore", invalid="ignore"):
            if compounding == "continuous":
                r = np.where(t > 1e-10, -np.log(df) / t, 0.0)
            elif compounding == "simple":
                r = np.where(t > 1e-10, (1.0 / df - 1.0) / t, 0.0)
            elif compounding == "annual":
                r = np.where(t > 1e-10, df ** (-1.0 / t) - 1.0, 0.0)
            else:
                raise ValueError(f"Unknown compounding: {compounding}")
        return r

    def forward_rate(
        self,
        t1: float | np.ndarray,
        t2: float | np.ndarray,
        compounding: str = "continuous",
    ) -> np.ndarray:
        """
        Simply-compounded or continuously-compounded forward rate f(t1, t2).

        compounding:
            'continuous' : f = (z(t2)*t2 - z(t1)*t1) / (t2 - t1)
            'simple'     : f = (DF(t1)/DF(t2) - 1) / (t2 - t1)
        """
        t1 = np.atleast_1d(np.asarray(t1, dtype=float))
        t2 = np.atleast_1d(np.asarray(t2, dtype=float))
        dt = t2 - t1

        df1 = self.discount_factor(t1)
        df2 = self.discount_factor(t2)

        with np.errstate(divide="ignore", invalid="ignore"):
            if compounding == "continuous":
                f = np.where(dt > 1e-10, np.log(df1 / df2) / dt, 0.0)
            elif compounding == "simple":
                f = np.where(dt > 1e-10, (df1 / df2 - 1.0) / dt, 0.0)
            else:
                raise ValueError(f"Unknown compounding: {compounding}")
        return f

    # ------------------------------------------------------------------
    # Summary / display
    # ------------------------------------------------------------------

    def summary(self, tenors_yr: List[float] | None = None) -> pd.DataFrame:
        """
        Return a DataFrame with Zero Rate (%), Discount Factor, Forward Rate (%)
        for a list of year-fraction tenors.

        Forward rate is the instantaneous 3-month forward (t, t+0.25).
        """
        if tenors_yr is None:
            tenors_yr = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]

        t = np.array(tenors_yr)
        zr = self.zero_rate(t, compounding="continuous") * 100
        df = self.discount_factor(t)
        # 3-month forward rate starting at each t
        fwd = self.forward_rate(t, t + 0.25, compounding="simple") * 100

        labels = []
        for tv in tenors_yr:
            if tv < 1:
                labels.append(f"{int(round(tv*12))}M")
            else:
                labels.append(f"{int(tv)}Y")

        return pd.DataFrame(
            {"Tenor": labels, "Zero Rate (%)": zr, "Discount Factor": df,
             "3M Fwd Rate (%)": fwd}
        ).set_index("Tenor")

    def __repr__(self) -> str:
        return f"<{self.name} | valuation={self.valuation_date} | pillars={len(self._times)-1}>"
