"""
Interest Rate Curve Builder – Streamlit UI
==========================================
직접 입력을 통해 USD SOFR IRS / KRW CD IRS 커브를 빌드하고
Zero Rate, Discount Factor, Forward Rate를 시각화합니다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
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

try:
    if uploaded_xlsx is not None:
        _data = _load_from_bytes(uploaded_xlsx.getvalue())
        _src = uploaded_xlsx.name
    else:
        _data = None

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

def make_chart(tenors_yr, curve, title):
    """
    tenors_yr : 희소 테너 리스트 (Summary 테이블용 / 마커 위치)
    내부적으로 300pt 고밀도 그리드를 생성해 MC 2차 곡선을 부드럽게 표현.
    Returns (fig, csv_df) — Plotly figure + CSV 다운로드용 DataFrame.
    """
    # ── 고밀도 그리드: 선(line) 용 ────────────────────────────────────
    t_min = max(tenors_yr[0], 1e-4)
    t_max = tenors_yr[-1]
    t_dense = np.linspace(t_min, t_max, 300)

    zeros_d = [curve.zero_rate(t)[0] * 100        for t in t_dense]
    dfs_d   = [curve.discount_factor(t)[0]         for t in t_dense]
    fwds_d  = [curve.forward_rate(t, t + 0.25)[0] * 100 for t in t_dense]

    # CSV 용 DataFrame
    csv_df = pd.DataFrame({
        "Tenor (years)": np.round(t_dense, 6),
        "Zero Rate (%)": np.round(zeros_d, 8),
        "Discount Factor": np.round(dfs_d, 10),
        "3M Forward Rate (%)": np.round(fwds_d, 8),
    })

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=t_dense, y=zeros_d, mode="lines",
        name="Zero Rate (%)", line=dict(color="#1f77b4", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=t_dense, y=fwds_d, mode="lines",
        name="3M Fwd Rate (%)", line=dict(color="#ff7f0e", width=2, dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=t_dense, y=dfs_d, mode="lines",
        name="Discount Factor", line=dict(color="#2ca02c", width=2),
        yaxis="y2",
    ))

    fig.update_layout(
        title=title,
        xaxis=dict(title="Tenor (years)"),
        yaxis=dict(title="Rate (%)", tickformat=".2f"),
        yaxis2=dict(title="Discount Factor", overlaying="y", side="right",
                    tickformat=".4f"),
        legend=dict(x=0.6, y=0.95),
        hovermode="x unified",
        height=420,
    )
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


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_usd, tab_krw, tab_ktb = st.tabs(["🇺🇸 USD SOFR IRS", "🇰🇷 KRW CD IRS", "🇰🇷 KRW KTB (국고채)"])

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
        if build_usd:
            try:
                ois_quotes  = dict(zip(usd_ois_input["Tenor"],  usd_ois_input["Rate (%)"]  / 100))
                swap_quotes = dict(zip(usd_swap_input["Tenor"], usd_swap_input["Rate (%)"] / 100))

                curve = USDSOFRCurve(
                    valuation_date=usd_val_date,
                    ois_quotes=ois_quotes,
                    swap_quotes=swap_quotes,
                )

                st.success(f"커브 빌드 완료: {curve}")

                # Summary
                tenors_yr = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
                summary = curve.summary(tenors_yr)
                st.subheader("Curve Summary")
                st.dataframe(summary, use_container_width=True)

                # Chart
                fig, csv_df = make_chart(tenors_yr, curve, "USD SOFR IRS Curve")
                st.plotly_chart(fig, use_container_width=True)

                st.download_button(
                    label="📥 Download Curve CSV",
                    data=csv_df.to_csv(index=False),
                    file_name="usd_sofr_curve.csv",
                    mime="text/csv",
                    key="usd_csv_download",
                )

                # Validation
                st.subheader("Validation (Implied vs Input)")
                all_quotes = {**ois_quotes, **swap_quotes}
                vdf = validation_df(curve, all_quotes)
                st.dataframe(
                    vdf.style.background_gradient(
                        subset=["Error (bps)"], cmap="RdYlGn_r", vmin=-0.5, vmax=0.5
                    ),
                    use_container_width=True,
                )

            except Exception as e:
                st.error(f"오류: {e}")
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
        if build_krw:
            try:
                swap_quotes = dict(zip(krw_swap_input["Tenor"], krw_swap_input["Rate (%)"] / 100))

                curve = KRWCDCurve(
                    valuation_date=krw_val_date,
                    cd_rate=krw_cd_rate / 100,
                    swap_quotes=swap_quotes,
                )

                st.success(f"커브 빌드 완료: {curve}")

                # Summary
                tenors_yr = [3/12, 6/12, 1, 2, 3, 5, 7, 10, 15, 20, 30]
                summary = curve.summary(tenors_yr)
                st.subheader("Curve Summary")
                st.dataframe(summary, use_container_width=True)

                # Chart
                fig, csv_df = make_chart(tenors_yr, curve, "KRW CD IRS Curve")
                st.plotly_chart(fig, use_container_width=True)

                st.download_button(
                    label="📥 Download Curve CSV",
                    data=csv_df.to_csv(index=False),
                    file_name="krw_cd_curve.csv",
                    mime="text/csv",
                    key="krw_csv_download",
                )

                # Validation
                st.subheader("Validation (Implied vs Input)")
                vdf = validation_df(curve, swap_quotes)
                st.dataframe(
                    vdf.style.background_gradient(
                        subset=["Error (bps)"], cmap="RdYlGn_r", vmin=-0.5, vmax=0.5
                    ),
                    use_container_width=True,
                )

            except Exception as e:
                st.error(f"오류: {e}")
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
        if build_ktb:
            try:
                bond_quotes = dict(zip(ktb_bond_input["Tenor"], ktb_bond_input["Rate (%)"] / 100))

                curve = KRWKTBCurve(
                    valuation_date=ktb_val_date,
                    bond_quotes=bond_quotes,
                    short_rate_3m=ktb_short_rate_3m / 100,
                    short_rate_6m=ktb_short_rate_6m / 100,
                )

                st.success(f"커브 빌드 완료: {curve}")

                # Summary — 3M·6M 단기 + 입력 테너 전체 포함 (최대 50Y)
                max_tenor = max(tenor_to_years(t) for t in bond_quotes)
                long_tenors = [y for y in [1, 2, 3, 5, 7, 10, 15, 20, 30, 50]
                               if y <= max_tenor + 1e-9]
                tenors_yr = [3/12, 6/12] + long_tenors
                summary = curve.summary(tenors_yr)
                st.subheader("Curve Summary")
                st.dataframe(summary, use_container_width=True)

                # Chart
                fig, csv_df = make_chart(tenors_yr, curve, "KRW KTB (국고채) Curve")
                st.plotly_chart(fig, use_container_width=True)

                st.download_button(
                    label="📥 Download Curve CSV",
                    data=csv_df.to_csv(index=False),
                    file_name="krw_ktb_curve.csv",
                    mime="text/csv",
                    key="ktb_csv_download",
                )

                # Validation — 국고채 Par Yield 역산 (단기채는 단리로 부트스트랩되어 제외)
                st.subheader("Validation (Implied vs Input)")
                vdf = validation_df(curve, bond_quotes)
                st.dataframe(
                    vdf.style.background_gradient(
                        subset=["Error (bps)"], cmap="RdYlGn_r", vmin=-0.5, vmax=0.5
                    ),
                    use_container_width=True,
                )

            except Exception as e:
                st.error(f"오류: {e}")
        else:
            st.info("왼쪽에서 국고채 수익률을 입력하고 **Build** 버튼을 누르세요.")
