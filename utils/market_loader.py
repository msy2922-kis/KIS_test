"""
시장 금리 엑셀 → 커브 입력 데이터 로더
========================================
시장 금리 시계열 형식의 워크북을 읽어 커브 부트스트래핑 입력(dict)으로 변환한다.

시트 공통 구조:
  R5  : 테너 라벨 ('1y IRS', '3m KTB', 'CD수익률', ...)
  R6  : 종목 코드
  R9~ : 일별 데이터 (col A = 날짜, 주말은 직전 영업일 값 carry-forward)

제공 함수:
  load_rates_workbook(src)          → {curve_key: DataFrame(index=date, cols=tenor label)}
  get_business_dates(data)          → 영업일 목록 (주말 제거, 오름차순)
  get_market_snapshot(data, asof)   → 커브별 입력 dict (금리 단위: %)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Union, IO

import pandas as pd

# 커브 키 → 시트명 부분 일치 패턴 (시트 이름이 패턴을 포함하면 매칭)
SHEET_PATTERNS = {
    "usd_sofr": "SOFR IRS",
    "krw_irs": "KRW Rates(IRS)",
    "krw_ktb": "KRW Treasury",
}

_HEADER_ROW = 5   # 테너 라벨 행 (1-indexed)
_DATA_START = 9   # 데이터 시작 행 (1-indexed)


# ---------------------------------------------------------------------------
# 라벨 → 표준 테너 변환
# ---------------------------------------------------------------------------

def _parse_label(label: str) -> Optional[str]:
    """
    '1y IRS' → '1Y', '1.5y KTB' → '1.5Y', '6m IRS' → '6M'.
    'CD수익률', 'SOFR rate', 'SOFR 3m' 등 비테너 라벨은 그대로 반환.
    """
    if label is None:
        return None
    s = str(label).strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([ymYM])\b", s)
    if m:
        num, unit = m.group(1), m.group(2).upper()
        # '1.0Y' → '1Y'
        if "." in num and float(num).is_integer():
            num = str(int(float(num)))
        return f"{num}{unit}"
    return s  # 'CD수익률', 'SOFR rate', 'SOFR 3m' 등


def _resolve_sheets(sheet_names: List[str]) -> Dict[str, str]:
    """커브 키 → 실제 시트명 매핑. 패턴을 포함하는 첫 시트를 사용."""
    resolved: Dict[str, str] = {}
    for key, pattern in SHEET_PATTERNS.items():
        for name in sheet_names:
            if pattern in name:
                resolved[key] = name
                break
        else:
            raise ValueError(
                f"'{pattern}' 이름을 포함하는 시트를 찾을 수 없습니다. "
                f"(발견된 시트: {sheet_names})"
            )
    return resolved


# ---------------------------------------------------------------------------
# 워크북 로드
# ---------------------------------------------------------------------------

def load_rates_workbook(src: Union[str, IO[bytes]]) -> Dict[str, pd.DataFrame]:
    """
    엑셀 파일(경로 또는 파일 객체)을 읽어 커브 키별 DataFrame으로 반환.

    Returns
    -------
    dict : {curve_key: DataFrame}   # curve_key ∈ {'usd_sofr', 'krw_irs', 'krw_ktb'}
        index  = 날짜(date, 주말 포함 원본 그대로)
        columns = 표준화된 테너 라벨 ('1Y', '1.5Y', 'CD수익률', ...)
        values  = 금리(%) 원값
    """
    xls = pd.ExcelFile(src, engine="openpyxl")
    sheets = _resolve_sheets(xls.sheet_names)

    result: Dict[str, pd.DataFrame] = {}
    for key, sheet in sheets.items():
        raw = xls.parse(sheet_name=sheet, header=None)

        labels = raw.iloc[_HEADER_ROW - 1]          # R5
        frames: Dict[str, pd.Series] = {}

        dates = pd.to_datetime(raw.iloc[_DATA_START - 1:, 0], errors="coerce")
        valid = dates.notna()

        for col in range(1, raw.shape[1]):
            tenor = _parse_label(labels.iloc[col])
            if not tenor or tenor == "nan":
                continue
            series = pd.to_numeric(
                raw.iloc[_DATA_START - 1:, col], errors="coerce"
            )
            frames[tenor] = series[valid].values

        df = pd.DataFrame(frames, index=[d.date() for d in dates[valid]])
        df = df[~df.index.duplicated(keep="last")]
        result[key] = df

    return result


def get_business_dates(data: Dict[str, pd.DataFrame]) -> List[date]:
    """전 시트 공통 영업일(주말 제거) 목록, 오름차순."""
    common = None
    for df in data.values():
        idx = set(d for d in df.index if d.weekday() < 5)
        common = idx if common is None else (common & idx)
    return sorted(common or [])


# ---------------------------------------------------------------------------
# 스냅샷 → 커브 입력
# ---------------------------------------------------------------------------

def get_market_snapshot(data: Dict[str, pd.DataFrame], asof: date) -> Dict:
    """
    특정 기준일의 커브 입력 데이터를 반환한다. 금리 단위는 % (UI 표시용).

    Returns
    -------
    {
      "asof": date,
      "usd_sofr": {"ois": {"1D": %, "3M": %}, "swap": {"1Y": %, ..., "30Y": %}},
      "krw_cd":   {"cd_rate": %, "swap": {"6M": %, ..., "30Y": %}},
      "krw_ktb":  {"short_3m": %, "short_6m": %, "bonds": {"1Y": %, ..., "50Y": %}},
    }
    """
    def row(key: str) -> pd.Series:
        df = data[key]
        if asof not in df.index:
            raise KeyError(f"'{key}' 데이터에 {asof} 기준일이 없습니다.")
        return df.loc[asof]

    # --- USD SOFR ---
    sofr = row("usd_sofr")
    usd_ois: Dict[str, float] = {}
    if pd.notna(sofr.get("SOFR rate")):
        usd_ois["1D"] = float(sofr["SOFR rate"])      # O/N SOFR
    if pd.notna(sofr.get("SOFR 3m")):
        usd_ois["3M"] = float(sofr["SOFR 3m"])        # 3M compound SOFR
    usd_swap = {
        t: float(sofr[t])
        for t in ["1Y", "2Y", "3Y", "5Y", "10Y", "15Y", "20Y", "30Y"]
        if t in sofr.index and pd.notna(sofr[t])
    }

    # --- KRW CD IRS ---
    irs = row("krw_irs")
    krw_swap = {
        t: float(irs[t])
        for t in ["6M", "1Y", "1.5Y", "2Y", "3Y", "4Y", "5Y",
                  "7Y", "10Y", "15Y", "20Y", "30Y"]
        if t in irs.index and pd.notna(irs[t])
    }
    cd_rate = float(irs["CD수익률"]) if pd.notna(irs.get("CD수익률")) else None

    # --- KRW KTB ---
    ktb = row("krw_ktb")
    ktb_bonds = {
        t: float(ktb[t])
        for t in ["1Y", "1.5Y", "2Y", "3Y", "4Y", "5Y",
                  "7Y", "10Y", "15Y", "20Y", "30Y", "50Y"]
        if t in ktb.index and pd.notna(ktb[t])
    }
    short_3m = float(ktb["3M"]) if pd.notna(ktb.get("3M")) else None
    short_6m = float(ktb["6M"]) if pd.notna(ktb.get("6M")) else None

    return {
        "asof": asof,
        "usd_sofr": {"ois": usd_ois, "swap": usd_swap},
        "krw_cd": {"cd_rate": cd_rate, "swap": krw_swap},
        "krw_ktb": {"short_3m": short_3m, "short_6m": short_6m, "bonds": ktb_bonds},
    }
