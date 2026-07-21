"""
Interest Rate Curve Builder – Streamlit UI
==========================================
USD SOFR IRS / KRW CD IRS / KRW KTB 커브를 빌드하고
Zero Rate, Discount Factor, Forward Rate를 시각화합니다.

- 빌드 결과는 session_state에 보존되어 위젯 조작·탭 전환에도 유지됨
- 차트는 화이트 배경(plotly_white) + 2단 서브플롯, theme=None으로 렌더
- Compare 탭에서 커브 오버레이 및 IRS−KTB 스왑 스프레드 제공
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date

from curves.usd_sofr_curve import USDSOFRCurve
from curves.krw_cd_curve import KRWCDCurve
from curves.krw_ktb_curve import KRWKTBCurve
from utils.day_count import tenor_to_years
from utils.market_loader import (
    load_rates_workbook, get_business_dates, get_market_snapshot,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="IR Curve Builder",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Interest Rate Curve Builder")
st.caption("USD SOFR IRS / KRW CD IRS / KRW KTB 커브 부트스트래핑 도구")

# 차트 색상 (화이트 배경 기준)
C_ZERO, C_FWD, C_DF = "#1f77b4", "#ff7f0e", "#2ca02c"
CURVE_META = [
    ("usd", "USD SOFR IRS", "#1f77b4"),
    ("cd", "KRW CD IRS", "#d62728"),
    ("ktb", "KRW KTB", "#2ca02c"),
]

# ---------------------------------------------------------------------------
# Sidebar: 시장 금리 엑셀 로더 (업로드 전용 — 데이터 파일은 레포에 저장하지 않음)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="엑셀 로드 중...")
def _load_from_bytes(file_bytes: bytes):
    import io
    return load_rates_workbook(io.BytesIO(file_bytes))


st.sidebar.header("📂 시장 데이터")
uploaded_xlsx = st.sidebar.file_uploader(
    "시장 금리 엑셀 업로드", type=["xlsx"], key="rates_uploader",
)

market = None          # 선택된 기준일의 커브 입력 스냅샷
mkey = "manual"        # 위젯 key 접미사 (데이터 소스·날짜 변경 시 입력 테이블 리셋)
_data, _bdays = None, []

try:
    if uploaded_xlsx is not None:
        _data = _load_from_bytes(uploaded_xlsx.getvalue())
        _src = uploaded_xlsx.name

    if _data:
        _bdays = get_business_dates(_data)
        sel_date = st.sidebar.selectbox(
            "기준일 선택 (영업일)",
            options=list(reversed(_bdays)),
            format_func=lambda d: d.strftime("%Y-%m-%d (%a)"),
            key="rates_asof",
        )
        market = get_market_snapshot(_data, sel_date)
        mkey = f"{_src}_{sel_date}"
        st.sidebar.success(f"✅ {_src}\n기준일 {sel_date} 로드 완료")
    else:
        st.sidebar.info("시장 금리 엑셀을 업로드하면\n시장 데이터가 자동 입력됩니다.")
except Exception as e:
    st.sidebar.error(f"로드 실패: {e}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def white_layout(fig, title, height=560):
    """화이트 배경 공통 스타일 (Streamlit 테마 오버라이드 방지: theme=None으로 렌더)."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#222222"),
        title=dict(text=title, font=dict(size=16)),
        hovermode="x unified",
        height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        margin=dict(l=60, r=30, t=70, b=40),
    )
    fig.update_xaxes(gridcolor="#e8e8e8", zerolinecolor="#cccccc", linecolor="#999999")
    fig.update_yaxes(gridcolor="#e8e8e8", zerolinecolor="#cccccc", linecolor="#999999")
    return fig


def curve_figure(curve, t_lo, t_hi, title):
    """
    2단 서브플롯: 상단 Zero + 3M Fwd (%), 하단 Discount Factor.
    300pt 고밀도 그리드로 MC 곡선을 부드럽게 표현. Returns (fig, csv_df).
    """
    t_dense = np.linspace(max(t_lo, 1e-4), t_hi, 300)
    zeros = [curve.zero_rate(t)[0] * 100 for t in t_dense]
    dfs = [curve.discount_factor(t)[0] for t in t_dense]
    fwds = [curve.forward_rate(t, t + 0.25)[0] * 100 for t in t_dense]

    csv_df = pd.DataFrame({
        "Tenor (years)": np.round(t_dense, 6),
        "Zero Rate (%)": np.round(zeros, 8),
        "Discount Factor": np.round(dfs, 10),
        "3M Forward Rate (%)": np.round(fwds, 8),
    })

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.62, 0.38], vertical_spacing=0.08,
        subplot_titles=("Zero Rate & 3M Forward (%)", "Discount Factor"),
    )
    fig.add_trace(go.Scatter(
        x=t_dense, y=zeros, mode="lines",
        name="Zero Rate (%)", line=dict(color=C_ZERO, width=2.2),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=t_dense, y=fwds, mode="lines",
        name="3M Fwd Rate (%)", line=dict(color=C_FWD, width=2, dash="dash"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=t_dense, y=dfs, mode="lines",
        name="Discount Factor", line=dict(color=C_DF, width=2),
    ), row=2, col=1)

    white_layout(fig, title)
    fig.update_yaxes(tickformat=".2f", row=1, col=1)
    fig.update_yaxes(tickformat=".4f", row=2, col=1)
    fig.update_xaxes(title_text="Tenor (years)", row=2, col=1)
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.07), row=2, col=1)
    return fig, csv_df


def validation_df(curve, quotes_dict):
    rows = []
    for tenor, input_rate in quotes_dict.items():
        try:
            implied = curve.par_swap_rate(tenor)
            error_bps = (implied - input_rate) * 10_000
            rows.append({
                "Tenor": tenor,
                "Input Rate (%)": round(input_rate * 100, 4),
                "Implied Rate (%)": round(implied * 100, 4),
                "Error (bps)": round(error_bps, 4),
            })
        except Exception:
            pass
    return pd.DataFrame(rows)


def kpi_cards(curve, prev_curve=None):
    """주요 테너 Zero + 10Y−2Y 기울기 메트릭 카드. prev_curve가 있으면 전일 대비 Δbp 표시."""
    t_max = float(curve._times[-1])
    items = []
    for t, lbl in [(0.25, "3M Zero"), (2.0, "2Y Zero"), (10.0, "10Y Zero"), (30.0, "30Y Zero")]:
        if t <= t_max + 1e-9:
            z = float(curve.zero_rate(t)[0]) * 100
            delta = None
            if prev_curve is not None:
                delta = (z - float(prev_curve.zero_rate(t)[0]) * 100) * 100  # bp
            items.append((lbl, f"{z:.4f}%", f"{delta:+.1f}bp" if delta is not None else None))
    if 10.0 <= t_max + 1e-9:
        slope = (float(curve.zero_rate(10.0)[0]) - float(curve.zero_rate(2.0)[0])) * 10_000
        sdelta = None
        if prev_curve is not None:
            prev_slope = (float(prev_curve.zero_rate(10.0)[0])
                          - float(prev_curve.zero_rate(2.0)[0])) * 10_000
            sdelta = slope - prev_slope
        items.append(("10Y−2Y", f"{slope:+.1f}bp", f"{sdelta:+.1f}bp" if sdelta is not None else None))

    cols = st.columns(len(items))
    for col, (lbl, val, dl) in zip(cols, items):
        col.metric(lbl, val, delta=dl)


def render_validation(curve, quotes, note=None):
    """No-Arbitrage 요약 배지 + expander 상세."""
    vdf = validation_df(curve, quotes)
    if vdf.empty:
        return
    max_err = vdf["Error (bps)"].abs().max()
    if max_err < 0.5:
        st.success(f"✅ No-Arbitrage 검증 통과 — 최대 역산 오차 {max_err:.4f} bps")
    else:
        st.error(f"❌ No-Arbitrage 위반 — 최대 역산 오차 {max_err:.4f} bps")
    with st.expander("Validation 상세 (Implied vs Input)"):
        st.dataframe(
            vdf.style.background_gradient(
                subset=["Error (bps)"], cmap="RdYlGn_r", vmin=-0.5, vmax=0.5
            ),
            use_container_width=True,
        )
        if note:
            st.caption(note)


def render_result(entry, title, csv_name, dl_key, validation_note=None):
    """세션에 저장된 빌드 결과 렌더 (KPI → 차트 → 검증 → Summary → CSV)."""
    curve = entry["curve"]
    st.caption(
        f"기준일 **{entry['asof']}** 빌드 · 필라 {len(curve._times) - 1}개"
        + (" · 전일 대비 Δ 표시 중" if entry.get("prev_curve") is not None else "")
    )
    kpi_cards(curve, entry.get("prev_curve"))

    fig, csv_df = curve_figure(curve, entry["t_lo"], entry["t_hi"], title)
    st.plotly_chart(fig, use_container_width=True, theme=None)

    render_validation(curve, entry["quotes"], validation_note)

    st.subheader("Curve Summary")
    summary = curve.summary(entry["tenors_yr"])
    st.dataframe(
        summary.style.format({
            "Zero Rate (%)": "{:.4f}",
            "Discount Factor": "{:.6f}",
            "3M Fwd Rate (%)": "{:.4f}",
        }),
        use_container_width=True,
    )

    st.download_button(
        label="📥 Download Curve CSV",
        data=csv_df.to_csv(index=False),
        file_name=csv_name,
        mime="text/csv",
        key=dl_key,
    )


def _editor_to_dict(df):
    """data_editor DataFrame → {tenor: rate%} (빈 행 제거)."""
    df = df.dropna(subset=["Tenor", "Rate (%)"])
    return {str(t): float(r) for t, r in zip(df["Tenor"], df["Rate (%)"])}


def _sig(val_date, *dicts):
    """입력 시그니처 — 저장된 빌드와 현재 입력의 불일치(stale) 감지용."""
    parts = [str(val_date)]
    for d in dicts:
        parts.append(tuple(sorted((str(k), round(float(v), 10)) for k, v in d.items())))
    return tuple(parts)


def prev_business_snapshot():
    """엑셀 로드 시 선택 기준일의 직전 영업일 스냅샷 (없으면 None)."""
    if not market or not _bdays:
        return None
    try:
        i = _bdays.index(market["asof"])
        if i == 0:
            return None
        return get_market_snapshot(_data, _bdays[i - 1])
    except Exception:
        return None


def _mk_usd(snap):
    return USDSOFRCurve(
        snap["asof"],
        {k: v / 100 for k, v in snap["usd_sofr"]["ois"].items()},
        {k: v / 100 for k, v in snap["usd_sofr"]["swap"].items()},
    )


def _mk_cd(snap):
    return KRWCDCurve(
        snap["asof"],
        snap["krw_cd"]["cd_rate"] / 100,
        {k: v / 100 for k, v in snap["krw_cd"]["swap"].items()},
    )


def _mk_ktb(snap):
    return KRWKTBCurve(
        snap["asof"],
        {k: v / 100 for k, v in snap["krw_ktb"]["bonds"].items()},
        short_rate_3m=snap["krw_ktb"]["short_3m"] / 100,
        short_rate_6m=snap["krw_ktb"]["short_6m"] / 100,
    )


def build_prev_curve(builder):
    """전일 스냅샷으로 비교용 커브 빌드 (실패 시 None)."""
    snap_prev = prev_business_snapshot()
    if snap_prev is None:
        return None
    try:
        return builder(snap_prev)
    except Exception:
        return None


st.session_state.setdefault("curves", {})

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_usd, tab_krw, tab_ktb, tab_cmp = st.tabs(
    ["🇺🇸 USD SOFR IRS", "🇰🇷 KRW CD IRS", "🇰🇷 KRW KTB (국고채)", "📊 Compare"]
)

# ===========================================================================
# USD SOFR Tab
# ===========================================================================
with tab_usd:
    col_in, col_out = st.columns([1, 2], gap="large")

    with col_in:
        st.subheader("Valuation Date")
        usd_val_date = st.date_input(
            "기준일",
            value=market["asof"] if market else date(2024, 3, 19),
            key=f"usd_val_date_{mkey}",
        )

        st.subheader("OIS Quotes (≤ 1Y)")
        if market:
            _ois = market["usd_sofr"]["ois"]
            usd_ois_default = pd.DataFrame({
                "Tenor": list(_ois.keys()),
                "Rate (%)": list(_ois.values()),
            })
        else:
            usd_ois_default = pd.DataFrame({
                "Tenor": ["1M", "3M", "6M", "1Y"],
                "Rate (%)": [5.31, 5.33, 5.27, 5.02],
            })
        usd_ois_input = st.data_editor(
            usd_ois_default,
            use_container_width=True,
            num_rows="dynamic",
            key=f"usd_ois_editor_{mkey}",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                ),
            },
        )

        st.subheader("Swap Quotes (> 1Y)")
        if market:
            _swap = market["usd_sofr"]["swap"]
            usd_swap_default = pd.DataFrame({
                "Tenor": list(_swap.keys()),
                "Rate (%)": list(_swap.values()),
            })
        else:
            usd_swap_default = pd.DataFrame({
                "Tenor": ["2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"],
                "Rate (%)": [4.68, 4.49, 4.37, 4.38, 4.40, 4.45, 4.45, 4.35],
            })
        usd_swap_input = st.data_editor(
            usd_swap_default,
            use_container_width=True,
            num_rows="dynamic",
            key=f"usd_swap_editor_{mkey}",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                ),
            },
        )

        build_usd = st.button("🔨 Build USD SOFR Curve", type="primary", use_container_width=True)

    with col_out:
        usd_ois_pct = _editor_to_dict(usd_ois_input)
        usd_swap_pct = _editor_to_dict(usd_swap_input)
        usd_cur_sig = _sig(usd_val_date, usd_ois_pct, usd_swap_pct)

        if build_usd:
            try:
                ois_quotes = {k: v / 100 for k, v in usd_ois_pct.items()}
                swap_quotes = {k: v / 100 for k, v in usd_swap_pct.items()}
                curve = USDSOFRCurve(
                    valuation_date=usd_val_date,
                    ois_quotes=ois_quotes,
                    swap_quotes=swap_quotes,
                )
                tenors_yr = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
                st.session_state["curves"]["usd"] = {
                    "curve": curve,
                    "prev_curve": build_prev_curve(_mk_usd),
                    "quotes": {**ois_quotes, **swap_quotes},
                    "raw_quotes": {**usd_ois_pct, **usd_swap_pct},
                    "tenors_yr": tenors_yr,
                    "t_lo": tenors_yr[0], "t_hi": tenors_yr[-1],
                    "asof": usd_val_date,
                    "sig": usd_cur_sig,
                }
                st.success(f"커브 빌드 완료: {curve}")
            except Exception as e:
                st.error(f"오류: {e}")

        entry = st.session_state["curves"].get("usd")
        if entry:
            if entry["sig"] != usd_cur_sig:
                st.warning("⚠️ 입력이 변경되었습니다 — **Build** 버튼을 다시 눌러 반영하세요.")
            render_result(entry, "USD SOFR IRS Curve", "usd_sofr_curve.csv", "usd_csv_download")
        else:
            st.info("왼쪽에서 시장 데이터를 입력하고 **Build** 버튼을 누르세요.")


# ===========================================================================
# KRW CD Tab
# ===========================================================================
with tab_krw:
    col_in, col_out = st.columns([1, 2], gap="large")

    with col_in:
        st.subheader("Valuation Date")
        krw_val_date = st.date_input(
            "기준일",
            value=market["asof"] if market else date(2024, 3, 19),
            key=f"krw_val_date_{mkey}",
        )

        st.subheader("CD 91일 금리")
        krw_cd_rate = st.number_input(
            "CD 91일 금리 (%)",
            value=float(market["krw_cd"]["cd_rate"]) if market else 3.68,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
            key=f"krw_cd_rate_{mkey}",
        )

        st.subheader("Swap Quotes")
        if market:
            _swap = market["krw_cd"]["swap"]
            krw_swap_default = pd.DataFrame({
                "Tenor": list(_swap.keys()),
                "Rate (%)": list(_swap.values()),
            })
        else:
            krw_swap_default = pd.DataFrame({
                "Tenor": ["6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"],
                "Rate (%)": [3.62, 3.53, 3.40, 3.35, 3.37, 3.42, 3.50, 3.60, 3.55],
            })
        krw_swap_input = st.data_editor(
            krw_swap_default,
            use_container_width=True,
            num_rows="dynamic",
            key=f"krw_swap_editor_{mkey}",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                ),
            },
        )

        build_krw = st.button("🔨 Build KRW CD Curve", type="primary", use_container_width=True)

    with col_out:
        krw_swap_pct = _editor_to_dict(krw_swap_input)
        krw_cur_sig = _sig(krw_val_date, {"CD": krw_cd_rate}, krw_swap_pct)

        if build_krw:
            try:
                swap_quotes = {k: v / 100 for k, v in krw_swap_pct.items()}
                curve = KRWCDCurve(
                    valuation_date=krw_val_date,
                    cd_rate=krw_cd_rate / 100,
                    swap_quotes=swap_quotes,
                )
                tenors_yr = [3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
                st.session_state["curves"]["cd"] = {
                    "curve": curve,
                    "prev_curve": build_prev_curve(_mk_cd),
                    "quotes": swap_quotes,
                    "raw_quotes": {"3M": krw_cd_rate, **krw_swap_pct},  # CD 91일 = 3M 앵커
                    "tenors_yr": tenors_yr,
                    "t_lo": tenors_yr[0], "t_hi": tenors_yr[-1],
                    "asof": krw_val_date,
                    "sig": krw_cur_sig,
                }
                st.success(f"커브 빌드 완료: {curve}")
            except Exception as e:
                st.error(f"오류: {e}")

        entry = st.session_state["curves"].get("cd")
        if entry:
            if entry["sig"] != krw_cur_sig:
                st.warning("⚠️ 입력이 변경되었습니다 — **Build** 버튼을 다시 눌러 반영하세요.")
            render_result(entry, "KRW CD IRS Curve", "krw_cd_curve.csv", "krw_csv_download")
        else:
            st.info("왼쪽에서 시장 데이터를 입력하고 **Build** 버튼을 누르세요.")


# ===========================================================================
# KRW KTB Tab
# ===========================================================================
with tab_ktb:
    col_in, col_out = st.columns([1, 2], gap="large")

    with col_in:
        st.subheader("Valuation Date")
        ktb_val_date = st.date_input(
            "기준일",
            value=market["asof"] if market else date(2024, 3, 19),
            key=f"ktb_val_date_{mkey}",
        )

        st.subheader("단기 기준금리 (단리, Simple Interest)")
        ktb_short_rate_3m = st.number_input(
            "3M 단기채 금리 (%)",
            value=float(market["krw_ktb"]["short_3m"]) if market else 3.55,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
            key=f"ktb_short_rate_3m_{mkey}",
        )
        ktb_short_rate_6m = st.number_input(
            "6M 단기채 금리 (%)",
            value=float(market["krw_ktb"]["short_6m"]) if market else 3.50,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
            key=f"ktb_short_rate_6m_{mkey}",
        )

        st.subheader("국고채 수익률 (Par Yield)")
        if market:
            _bonds = market["krw_ktb"]["bonds"]
            ktb_bond_default = pd.DataFrame({
                "Tenor": list(_bonds.keys()),
                "Rate (%)": list(_bonds.values()),
            })
        else:
            ktb_bond_default = pd.DataFrame({
                "Tenor": ["1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y", "50Y"],
                "Rate (%)": [3.45, 3.35, 3.30, 3.35, 3.50, 3.60, 3.55, 3.45],
            })
        ktb_bond_input = st.data_editor(
            ktb_bond_default,
            use_container_width=True,
            num_rows="dynamic",
            key=f"ktb_bond_editor_{mkey}",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                ),
            },
        )

        build_ktb = st.button("🔨 Build KRW KTB Curve", type="primary", use_container_width=True)

    with col_out:
        ktb_bond_pct = _editor_to_dict(ktb_bond_input)
        ktb_cur_sig = _sig(
            ktb_val_date, {"3M": ktb_short_rate_3m, "6M": ktb_short_rate_6m}, ktb_bond_pct
        )

        if build_ktb:
            try:
                bond_quotes = {k: v / 100 for k, v in ktb_bond_pct.items()}
                curve = KRWKTBCurve(
                    valuation_date=ktb_val_date,
                    bond_quotes=bond_quotes,
                    short_rate_3m=ktb_short_rate_3m / 100,
                    short_rate_6m=ktb_short_rate_6m / 100,
                )
                max_tenor = max(tenor_to_years(t) for t in bond_quotes)
                long_tenors = [y for y in [1, 2, 3, 5, 7, 10, 15, 20, 30, 50]
                               if y <= max_tenor + 1e-9]
                tenors_yr = [3/12, 6/12] + long_tenors
                st.session_state["curves"]["ktb"] = {
                    "curve": curve,
                    "prev_curve": build_prev_curve(_mk_ktb),
                    "quotes": bond_quotes,
                    "raw_quotes": {"3M": ktb_short_rate_3m, "6M": ktb_short_rate_6m,
                                   **ktb_bond_pct},
                    "tenors_yr": tenors_yr,
                    "t_lo": tenors_yr[0], "t_hi": tenors_yr[-1],
                    "asof": ktb_val_date,
                    "sig": ktb_cur_sig,
                }
                st.success(f"커브 빌드 완료: {curve}")
            except Exception as e:
                st.error(f"오류: {e}")

        entry = st.session_state["curves"].get("ktb")
        if entry:
            if entry["sig"] != ktb_cur_sig:
                st.warning("⚠️ 입력이 변경되었습니다 — **Build** 버튼을 다시 눌러 반영하세요.")
            render_result(
                entry, "KRW KTB (국고채) Curve", "krw_ktb_curve.csv", "ktb_csv_download",
                validation_note="단기채(3M·6M)는 단리로 부트스트랩되어 역산 비교에서 제외됩니다.",
            )
        else:
            st.info("왼쪽에서 국고채 수익률을 입력하고 **Build** 버튼을 누르세요.")


# ===========================================================================
# Compare Tab
# ===========================================================================
with tab_cmp:
    entries = st.session_state["curves"]
    built = [(k, name, color) for k, name, color in CURVE_META if k in entries]

    if not built:
        st.info("각 탭에서 커브를 빌드하면 여기에서 비교할 수 있습니다.")
    else:
        asofs = {name: entries[k]["asof"] for k, name, _ in built}
        if len(set(asofs.values())) > 1:
            st.warning("⚠️ 커브별 기준일이 다릅니다: "
                       + ", ".join(f"{n}={d}" for n, d in asofs.items()))

        # --- Zero 커브 오버레이 ---
        fig = go.Figure()
        for k, name, color in built:
            e = entries[k]
            t_dense = np.linspace(max(e["t_lo"], 1e-4), e["t_hi"], 300)
            zeros = [e["curve"].zero_rate(t)[0] * 100 for t in t_dense]
            fig.add_trace(go.Scatter(
                x=t_dense, y=zeros, mode="lines",
                name=f"{name} ({e['asof']})", line=dict(color=color, width=2.2),
            ))
        white_layout(fig, "Zero Curve Overlay (%)", height=440)
        fig.update_xaxes(title_text="Tenor (years)")
        fig.update_yaxes(tickformat=".2f")
        st.plotly_chart(fig, use_container_width=True, theme=None)

        # --- Raw 마켓 레이트 비교 (입력 원값, 보간 없음) ---
        st.subheader("Market Rates (Raw Input)")
        st.caption("각 탭에 입력된 만기별 마켓 레이트 원값 비교 — 보간·부트스트랩을 거치지 않은 호가 그대로입니다.")
        fig_raw = go.Figure()
        for k, name, color in built:
            e = entries[k]
            raw = e.get("raw_quotes") or {t: v * 100 for t, v in e["quotes"].items()}
            pts = []
            for tenor, rate in raw.items():
                try:
                    pts.append((tenor_to_years(tenor), tenor, float(rate)))
                except ValueError:
                    continue  # 테너 형식이 아닌 라벨은 스킵
            pts.sort(key=lambda p: p[0])
            fig_raw.add_trace(go.Scatter(
                x=[p[0] for p in pts],
                y=[p[2] for p in pts],
                mode="lines+markers",
                name=f"{name} ({e['asof']})",
                line=dict(color=color, width=1.5, dash="dot"),
                marker=dict(size=8, symbol="circle"),
                text=[p[1] for p in pts],
                hovertemplate="%{text}: %{y:.4f}%<extra>" + name + "</extra>",
            ))
        white_layout(fig_raw, "만기별 마켓 레이트 (Raw Input, %)", height=420)
        fig_raw.update_xaxes(title_text="Tenor (years)")
        fig_raw.update_yaxes(tickformat=".2f", title_text="Market Rate (%)")
        st.plotly_chart(fig_raw, use_container_width=True, theme=None)

        # --- IRS − KTB 스왑 스프레드 ---
        if "cd" in entries and "ktb" in entries:
            st.subheader("Swap Spread: IRS − KTB")
            e_cd, e_ktb = entries["cd"], entries["ktb"]
            t_lo = max(e_cd["t_lo"], e_ktb["t_lo"], 0.25)
            t_hi = min(e_cd["t_hi"], e_ktb["t_hi"])
            t_dense = np.linspace(t_lo, t_hi, 300)
            spread = [
                (e_cd["curve"].zero_rate(t)[0] - e_ktb["curve"].zero_rate(t)[0]) * 10_000
                for t in t_dense
            ]

            fig_sp = go.Figure()
            fig_sp.add_trace(go.Scatter(
                x=t_dense, y=spread, mode="lines",
                name="Zero Spread (bp)", line=dict(color="#7c4dff", width=2.2),
                fill="tozeroy", fillcolor="rgba(124,77,255,0.08)",
            ))
            white_layout(fig_sp, "IRS − KTB Zero Spread (bp)", height=380)
            fig_sp.update_xaxes(title_text="Tenor (years)")
            fig_sp.update_yaxes(tickformat=".1f", title_text="Spread (bp)")
            st.plotly_chart(fig_sp, use_container_width=True, theme=None)

            # 테너별 비교 테이블
            table_tenors = [t for t in [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50]
                            if t_lo - 1e-9 <= t <= t_hi + 1e-9]
            rows = []
            for t in table_tenors:
                zi = e_cd["curve"].zero_rate(t)[0] * 100
                zk = e_ktb["curve"].zero_rate(t)[0] * 100
                lbl = f"{int(round(t*12))}M" if t < 1 else f"{int(t)}Y"
                rows.append({
                    "Tenor": lbl,
                    "IRS Zero (%)": round(zi, 4),
                    "KTB Zero (%)": round(zk, 4),
                    "Spread (bp)": round((zi - zk) * 100, 2),
                })
            cmp_df = pd.DataFrame(rows).set_index("Tenor")
            st.dataframe(
                cmp_df.style.background_gradient(
                    subset=["Spread (bp)"], cmap="RdBu_r", vmin=-100, vmax=100
                ).format({
                    "IRS Zero (%)": "{:.4f}",
                    "KTB Zero (%)": "{:.4f}",
                    "Spread (bp)": "{:+.2f}",
                }),
                use_container_width=True,
            )
        else:
            st.caption("KRW CD IRS와 KRW KTB 커브를 모두 빌드하면 스왑 스프레드가 표시됩니다.")
