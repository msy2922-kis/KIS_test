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
# Helpers
# ---------------------------------------------------------------------------

def make_chart(tenors_yr, curve, title):
    zeros = [curve.zero_rate(t)[0] * 100 for t in tenors_yr]
    dfs   = [curve.discount_factor(t)[0] for t in tenors_yr]
    fwds  = [curve.forward_rate(t, t + 0.25)[0] * 100 for t in tenors_yr]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tenors_yr, y=zeros, mode="lines+markers",
                             name="Zero Rate (%)", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=tenors_yr, y=fwds,  mode="lines+markers",
                             name="3M Fwd Rate (%)", line=dict(color="#ff7f0e", dash="dash")))
    fig.add_trace(go.Scatter(x=tenors_yr, y=dfs,   mode="lines+markers",
                             name="Discount Factor", line=dict(color="#2ca02c"),
                             yaxis="y2"))

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
    return fig


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
            "기준일", value=date(2024, 3, 19), key="usd_val_date"
        )

        st.subheader("OIS Quotes (≤ 1Y)")
        usd_ois_default = pd.DataFrame({
            "Tenor": ["1M", "3M", "6M", "1Y"],
            "Rate (%)": [5.31, 5.33, 5.27, 5.02],
        })
        usd_ois_input = st.data_editor(
            usd_ois_default,
            use_container_width=True,
            num_rows="dynamic",
            key="usd_ois_editor",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.4f", min_value=0.0, max_value=50.0, step=0.01
                ),
            },
        )

        st.subheader("Swap Quotes (> 1Y)")
        usd_swap_default = pd.DataFrame({
            "Tenor": ["2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"],
            "Rate (%)": [4.68, 4.49, 4.37, 4.38, 4.40, 4.45, 4.45, 4.35],
        })
        usd_swap_input = st.data_editor(
            usd_swap_default,
            use_container_width=True,
            num_rows="dynamic",
            key="usd_swap_editor",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.4f", min_value=0.0, max_value=50.0, step=0.01
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
                st.plotly_chart(
                    make_chart(tenors_yr, curve, "USD SOFR IRS Curve"),
                    use_container_width=True,
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
            "기준일", value=date(2024, 3, 19), key="krw_val_date"
        )

        st.subheader("CD 91일 금리")
        krw_cd_rate = st.number_input(
            "CD 91일 금리 (%)",
            value=3.68,
            min_value=0.0,
            max_value=50.0,
            step=0.01,
            format="%.4f",
            key="krw_cd_rate",
        )

        st.subheader("Swap Quotes")
        krw_swap_default = pd.DataFrame({
            "Tenor": ["6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"],
            "Rate (%)": [3.62, 3.53, 3.40, 3.35, 3.37, 3.42, 3.50, 3.60, 3.55],
        })
        krw_swap_input = st.data_editor(
            krw_swap_default,
            use_container_width=True,
            num_rows="dynamic",
            key="krw_swap_editor",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.4f", min_value=0.0, max_value=50.0, step=0.01
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
                st.plotly_chart(
                    make_chart(tenors_yr, curve, "KRW CD IRS Curve"),
                    use_container_width=True,
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
            "기준일", value=date(2024, 3, 19), key="ktb_val_date"
        )

        st.subheader("단기 기준금리 (단리, Simple Interest)")
        ktb_short_rate_3m = st.number_input(
            "3M 단기채 금리 (%)",
            value=3.55,
            min_value=0.0,
            max_value=50.0,
            step=0.01,
            format="%.4f",
            key="ktb_short_rate_3m",
        )
        ktb_short_rate_6m = st.number_input(
            "6M 단기채 금리 (%)",
            value=3.50,
            min_value=0.0,
            max_value=50.0,
            step=0.01,
            format="%.4f",
            key="ktb_short_rate_6m",
        )

        st.subheader("국고채 수익률 (Par Yield)")
        ktb_bond_default = pd.DataFrame({
            "Tenor": ["1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y", "50Y"],
            "Rate (%)": [3.45, 3.35, 3.30, 3.35, 3.50, 3.60, 3.55, 3.45],
        })
        ktb_bond_input = st.data_editor(
            ktb_bond_default,
            use_container_width=True,
            num_rows="dynamic",
            key="ktb_bond_editor",
            column_config={
                "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                "Rate (%)": st.column_config.NumberColumn(
                    "Rate (%)", format="%.4f", min_value=0.0, max_value=50.0, step=0.01
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
                max_tenor = max(
                    {"1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "10Y": 10,
                     "20Y": 20, "30Y": 30, "50Y": 50}.get(t, 1)
                    for t in bond_quotes
                )
                long_tenors = [y for y in [1, 2, 3, 5, 7, 10, 15, 20, 30, 50]
                               if y <= max_tenor]
                tenors_yr = [3/12, 6/12] + long_tenors
                summary = curve.summary(tenors_yr)
                st.subheader("Curve Summary")
                st.dataframe(summary, use_container_width=True)

                # Chart
                st.plotly_chart(
                    make_chart(tenors_yr, curve, "KRW KTB (국고채) Curve"),
                    use_container_width=True,
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
