"""
Interest Rate Curve Builder & HW Calibration – Streamlit UI
=============================================================
직접 입력을 통해 USD SOFR IRS / KRW CD IRS 커브를 빌드하고
Zero Rate, Discount Factor, Forward Rate를 시각화합니다.
Hull-White 모델의 Curve Fitting 검증 및 캘리브레이션 기능을 포함합니다.
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
from calibration.hw_calibrator import HWCalibrator

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="IR Curve Builder",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Interest Rate Curve Builder & HW Calibration")
st.caption("USD SOFR IRS / KRW CD IRS / KRW KTB 커브 부트스트래핑 + Hull-White 캘리브레이션")

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
tab_usd, tab_krw, tab_ktb, tab_hw = st.tabs([
    "🇺🇸 USD SOFR IRS", "🇰🇷 KRW CD IRS", "🇰🇷 KRW KTB (국고채)", "🔧 HW Calibration"
])

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
                    "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
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
            "기준일", value=date(2024, 3, 19), key="krw_val_date"
        )

        st.subheader("CD 91일 금리")
        krw_cd_rate = st.number_input(
            "CD 91일 금리 (%)",
            value=3.68,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
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
            "기준일", value=date(2024, 3, 19), key="ktb_val_date"
        )

        st.subheader("단기 기준금리 (단리, Simple Interest)")
        ktb_short_rate_3m = st.number_input(
            "3M 단기채 금리 (%)",
            value=3.55,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
            key="ktb_short_rate_3m",
        )
        ktb_short_rate_6m = st.number_input(
            "6M 단기채 금리 (%)",
            value=3.50,
            min_value=0.0,
            max_value=50.0,
            format="%.10g",
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


# ===========================================================================
# Hull-White Calibration Tab
# ===========================================================================
with tab_hw:
    col_in, col_out = st.columns([1, 2], gap="large")

    with col_in:
        st.subheader("기초 커브 설정")

        hw_curve_type = st.selectbox(
            "커브 종류",
            ["KRW KTB (국고채)", "KRW CD IRS", "USD SOFR IRS"],
            key="hw_curve_type",
        )

        hw_val_date = st.date_input("기준일", value=date(2025, 3, 17), key="hw_val_date")

        if hw_curve_type == "KRW KTB (국고채)":
            hw_short_3m = st.number_input(
                "3M 단기채 금리 (%)", value=3.35, format="%.10g", key="hw_short_3m",
            )
            hw_short_6m = st.number_input(
                "6M 단기채 금리 (%)", value=2.90, format="%.10g", key="hw_short_6m",
            )
            hw_ktb_default = pd.DataFrame({
                "Tenor": ["1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"],
                "Rate (%)": [2.70, 2.65, 2.68, 2.80, 3.00, 2.95, 2.90],
            })
            hw_ktb_input = st.data_editor(
                hw_ktb_default, use_container_width=True, num_rows="dynamic",
                key="hw_ktb_editor",
                column_config={
                    "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                    "Rate (%)": st.column_config.NumberColumn(
                        "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                    ),
                },
            )
        elif hw_curve_type == "KRW CD IRS":
            hw_cd_rate = st.number_input(
                "CD 91일 금리 (%)", value=3.50, format="%.10g", key="hw_cd_rate",
            )
            hw_cd_swap_default = pd.DataFrame({
                "Tenor": ["6M", "1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"],
                "Rate (%)": [3.40, 3.30, 3.20, 3.18, 3.20, 3.30, 3.35, 3.30],
            })
            hw_cd_swap_input = st.data_editor(
                hw_cd_swap_default, use_container_width=True, num_rows="dynamic",
                key="hw_cd_swap_editor",
                column_config={
                    "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                    "Rate (%)": st.column_config.NumberColumn(
                        "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                    ),
                },
            )
        else:  # USD SOFR
            hw_usd_ois_default = pd.DataFrame({
                "Tenor": ["1M", "3M", "6M", "1Y"],
                "Rate (%)": [4.30, 4.25, 4.10, 3.90],
            })
            hw_usd_ois_input = st.data_editor(
                hw_usd_ois_default, use_container_width=True, num_rows="dynamic",
                key="hw_usd_ois_editor",
                column_config={
                    "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                    "Rate (%)": st.column_config.NumberColumn(
                        "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                    ),
                },
            )
            hw_usd_swap_default = pd.DataFrame({
                "Tenor": ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"],
                "Rate (%)": [3.80, 3.75, 3.70, 3.72, 3.75, 3.80, 3.70],
            })
            hw_usd_swap_input = st.data_editor(
                hw_usd_swap_default, use_container_width=True, num_rows="dynamic",
                key="hw_usd_swap_editor",
                column_config={
                    "Tenor": st.column_config.TextColumn("Tenor", width="small"),
                    "Rate (%)": st.column_config.NumberColumn(
                        "Rate (%)", format="%.10g", min_value=0.0, max_value=50.0,
                    ),
                },
            )

        st.divider()
        st.subheader("HW 파라미터 초기값")
        hw_kappa_init = st.number_input(
            "κ (Mean Reversion)", value=0.03, min_value=0.0001, max_value=2.0,
            step=0.01, format="%.4f", key="hw_kappa_init",
        )
        hw_sigma_init = st.number_input(
            "σ (Volatility)", value=0.01, min_value=0.0001, max_value=0.10,
            step=0.001, format="%.4f", key="hw_sigma_init",
        )

        st.divider()
        st.subheader("스왑션 Normal Vol (캘리브레이션 대상)")
        hw_vol_default = pd.DataFrame({
            "Expiry": [1.0, 1.0, 5.0, 5.0, 10.0],
            "Tenor": [1.0, 5.0, 5.0, 10.0, 10.0],
            "Vol (bps)": [45.0, 55.0, 50.0, 48.0, 46.0],
        })
        hw_vol_input = st.data_editor(
            hw_vol_default, use_container_width=True, num_rows="dynamic",
            key="hw_vol_editor",
            column_config={
                "Expiry": st.column_config.NumberColumn("Expiry (Y)", format="%.1f"),
                "Tenor": st.column_config.NumberColumn("Tenor (Y)", format="%.1f"),
                "Vol (bps)": st.column_config.NumberColumn(
                    "Normal Vol (bps)", format="%.1f", min_value=0.1, max_value=500.0,
                ),
            },
        )

        build_hw = st.button(
            "🔧 Build Curve & Calibrate", type="primary", use_container_width=True,
        )

    # ── 우측 결과 패널 ──────────────────────────────────────────────────
    with col_out:
        if build_hw:
            try:
                # ── 1. 커브 구축 ──────────────────────────────────────
                if hw_curve_type == "KRW KTB (국고채)":
                    bq = dict(zip(hw_ktb_input["Tenor"], hw_ktb_input["Rate (%)"] / 100))
                    hw_curve = KRWKTBCurve(
                        valuation_date=hw_val_date, bond_quotes=bq,
                        short_rate_3m=hw_short_3m / 100, short_rate_6m=hw_short_6m / 100,
                    )
                elif hw_curve_type == "KRW CD IRS":
                    sq = dict(zip(hw_cd_swap_input["Tenor"], hw_cd_swap_input["Rate (%)"] / 100))
                    hw_curve = KRWCDCurve(
                        valuation_date=hw_val_date, cd_rate=hw_cd_rate / 100, swap_quotes=sq,
                    )
                else:
                    oq = dict(zip(hw_usd_ois_input["Tenor"], hw_usd_ois_input["Rate (%)"] / 100))
                    sq = dict(zip(hw_usd_swap_input["Tenor"], hw_usd_swap_input["Rate (%)"] / 100))
                    hw_curve = USDSOFRCurve(
                        valuation_date=hw_val_date, ois_quotes=oq, swap_quotes=sq,
                    )

                st.success(f"커브 빌드 완료: {hw_curve}")

                # ── 2. Curve Fitting 검증 ────────────────────────────
                st.subheader("1. Curve Fitting 검증")
                calibrator = HWCalibrator(hw_curve, kappa=hw_kappa_init, sigma=hw_sigma_init)

                fit_tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]
                fit_df = calibrator.validate_curve_fit(fit_tenors)

                # DF 비교 차트
                fig_fit = go.Figure()
                fig_fit.add_trace(go.Scatter(
                    x=fit_tenors, y=fit_df["Market DF"].values,
                    mode="lines+markers", name="Market DF",
                    line=dict(color="#1f77b4", width=2),
                    marker=dict(size=6),
                ))
                fig_fit.add_trace(go.Scatter(
                    x=fit_tenors, y=fit_df["Model DF"].values,
                    mode="lines+markers", name="Model DF (HW)",
                    line=dict(color="#ff7f0e", width=2, dash="dash"),
                    marker=dict(size=6, symbol="x"),
                ))
                fig_fit.update_layout(
                    title="Market DF vs Hull-White Model DF",
                    xaxis_title="Tenor (years)", yaxis_title="Discount Factor",
                    yaxis_tickformat=".4f",
                    hovermode="x unified", height=350,
                    legend=dict(x=0.65, y=0.95),
                )
                st.plotly_chart(fig_fit, use_container_width=True)

                # Fitting Error 바 차트
                errors = fit_df["Abs Error"].values
                max_err = max(errors) if max(errors) > 0 else 1e-16
                fig_err = go.Figure()
                fig_err.add_trace(go.Bar(
                    x=[f"{t}Y" for t in fit_tenors], y=errors,
                    marker_color=["#2ca02c" if e < 1e-10 else "#ff7f0e" if e < 1e-6 else "#d62728"
                                  for e in errors],
                    text=[f"{e:.1e}" for e in errors],
                    textposition="outside",
                ))
                fig_err.update_layout(
                    title="Fitting Error by Tenor",
                    xaxis_title="Tenor", yaxis_title="Absolute Error",
                    yaxis_type="log" if max_err > 0 else "linear",
                    height=280,
                )
                st.plotly_chart(fig_err, use_container_width=True)

                max_error = fit_df["Abs Error"].max()
                if max_error < 1e-10:
                    st.success(f"PASS: 최대 Fitting 오차 = {max_error:.2e} (기준: < 1e-10)")
                else:
                    st.warning(f"최대 Fitting 오차 = {max_error:.2e}")

                st.dataframe(fit_df, use_container_width=True)

                # ── 3. 캘리브레이션 ──────────────────────────────────
                st.divider()
                st.subheader("2. (κ, σ) 캘리브레이션")

                market_instruments = []
                for _, row in hw_vol_input.iterrows():
                    market_instruments.append({
                        "type": "swaption",
                        "expiry": float(row["Expiry"]),
                        "tenor": float(row["Tenor"]),
                        "strike": "atm",
                        "market_vol": float(row["Vol (bps)"]) / 10000.0,
                    })

                with st.spinner("캘리브레이션 진행 중..."):
                    cal_result = calibrator.calibrate(market_instruments=market_instruments)

                # 메트릭 카드
                m1, m2, m3 = st.columns(3)
                m1.metric("κ (Mean Reversion)", f"{cal_result['kappa']:.6f}")
                m2.metric("σ (Volatility)", f"{cal_result['sigma']:.6f}")
                m3.metric("RMSE", f"{cal_result['rmse_bps']:.2f} bps")

                if cal_result["success"]:
                    st.success(f"수렴 성공: {cal_result['message']}")
                else:
                    st.warning(f"수렴 실패: {cal_result['message']}")

                # Market vs Model Vol 바 차트
                details = cal_result["details"]
                labels = [f"{int(r['Expiry'])}Y×{int(r['Tenor'])}Y" for _, r in details.iterrows()]

                fig_vol = go.Figure()
                fig_vol.add_trace(go.Bar(
                    x=labels, y=details["Market Vol (bps)"].values,
                    name="Market Vol", marker_color="#1f77b4",
                ))
                fig_vol.add_trace(go.Bar(
                    x=labels, y=details["Model Vol (bps)"].values,
                    name="Model Vol", marker_color="#ff7f0e",
                ))
                fig_vol.update_layout(
                    title="Market vs Model Swaption Normal Vol",
                    xaxis_title="Swaption (Expiry × Tenor)",
                    yaxis_title="Normal Vol (bps)",
                    barmode="group", height=350,
                    legend=dict(x=0.7, y=0.95),
                )
                st.plotly_chart(fig_vol, use_container_width=True)

                # 상세 결과
                st.dataframe(
                    details.style.background_gradient(
                        subset=["Error (bps)"], cmap="RdYlGn_r", vmin=-5, vmax=5,
                    ),
                    use_container_width=True,
                )

                # ── 캘리브레이션 후 Curve Fitting 재검증 ──────────────
                fit_df2 = calibrator.validate_curve_fit(fit_tenors)
                max_err2 = fit_df2["Abs Error"].max()
                if max_err2 < 1e-10:
                    st.success(f"캘리브레이션 후 Curve Fitting 유지: 최대 오차 = {max_err2:.2e}")
                else:
                    st.info(f"캘리브레이션 후 Curve Fitting 오차: {max_err2:.2e}")

                # ── 4. 파라미터 민감도 (κ-σ 등고선) ──────────────────
                st.divider()
                st.subheader("3. 파라미터 민감도 (κ-σ 목적함수)")

                show_contour = st.checkbox(
                    "등고선 계산 실행 (12×12 그리드, ~30초 소요)",
                    value=False, key="hw_show_contour",
                )

                if show_contour:
                    with st.spinner("등고선 계산 중..."):
                        k_opt, s_opt = cal_result["kappa"], cal_result["sigma"]

                        # 최적점에서의 시장 가격 사전 계산 (비교 기준)
                        market_prices = []
                        for inst in market_instruments:
                            T0 = inst["expiry"]
                            tenor = inst["tenor"]
                            K = inst.get("strike")
                            if K == "atm" or K is None:
                                K = calibrator._par_swap_rate_from_curve(T0, tenor, 0.5)
                            # Bachelier 공식으로 시장 가격 계산
                            n_pay = max(1, int(round(tenor / 0.5)))
                            annuity = sum(
                                0.5 * calibrator._P0(T0 + (i + 1) * 0.5)
                                for i in range(n_pay)
                            )
                            mkt_vol = inst["market_vol"]
                            from scipy.stats import norm as norm_dist
                            mkt_price = annuity * mkt_vol * np.sqrt(T0) * norm_dist.pdf(0)
                            market_prices.append({"T0": T0, "tenor": tenor, "K": K,
                                                  "price": mkt_price})

                        n_grid = 12
                        k_range = np.linspace(max(1e-4, k_opt * 0.3), min(2.0, k_opt * 3.0), n_grid)
                        s_range = np.linspace(max(1e-4, s_opt * 0.3), min(0.1, s_opt * 3.0), n_grid)
                        Z = np.zeros((n_grid, n_grid))

                        for i, s_val in enumerate(s_range):
                            for j, k_val in enumerate(k_range):
                                calibrator.kappa = k_val
                                calibrator.sigma = s_val
                                calibrator._build_model()
                                sse = 0.0
                                for mp in market_prices:
                                    try:
                                        model_px = calibrator.swaption_price(
                                            mp["T0"], mp["tenor"], mp["K"], 0.5, "payer")
                                        sse += (model_px - mp["price"]) ** 2
                                    except Exception:
                                        sse += 1.0
                                Z[i, j] = np.sqrt(sse / len(market_prices)) * 10000

                        # 최적 파라미터 복원
                        calibrator.kappa = k_opt
                        calibrator.sigma = s_opt
                        calibrator._build_model()

                    fig_contour = go.Figure()
                    fig_contour.add_trace(go.Contour(
                        x=k_range, y=s_range, z=Z,
                        colorscale="Viridis", reversescale=True,
                        contours=dict(showlabels=True, labelfont=dict(size=10)),
                        colorbar=dict(title="RMSE (price bps)"),
                    ))
                    fig_contour.add_trace(go.Scatter(
                        x=[k_opt], y=[s_opt], mode="markers+text",
                        marker=dict(size=14, color="red", symbol="star"),
                        text=["Optimal"], textposition="top center",
                        textfont=dict(color="red", size=12),
                        name="Optimal",
                    ))
                    fig_contour.update_layout(
                        title="목적함수 등고선 (RMSE)",
                        xaxis_title="κ (Mean Reversion)",
                        yaxis_title="σ (Volatility)",
                        height=450,
                    )
                    st.plotly_chart(fig_contour, use_container_width=True)
                else:
                    st.info("체크박스를 선택하면 κ-σ 등고선을 계산합니다.")

                # ── 5. 파생상품 가격 계산기 ──────────────────────────
                st.divider()
                st.subheader("4. 파생상품 가격 계산기")

                calc_type = st.radio(
                    "상품 유형", ["Swaption", "Cap"],
                    horizontal=True, key="hw_calc_type",
                )

                if calc_type == "Swaption":
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    calc_expiry = cc1.number_input(
                        "Expiry (Y)", value=1.0, min_value=0.25, step=0.5, key="calc_exp",
                    )
                    calc_tenor = cc2.number_input(
                        "Tenor (Y)", value=5.0, min_value=0.5, step=0.5, key="calc_tenor",
                    )
                    calc_strike_mode = cc3.selectbox(
                        "Strike", ["ATM", "Custom"], key="calc_strike_mode",
                    )
                    if calc_strike_mode == "Custom":
                        calc_strike = cc4.number_input(
                            "Strike Rate (%)", value=3.0, format="%.4f", key="calc_strike",
                        ) / 100.0
                    else:
                        calc_strike = None
                    calc_option_type = st.radio(
                        "Type", ["payer", "receiver"], horizontal=True, key="calc_opt_type",
                    )

                    if st.button("계산", key="calc_swaption_btn"):
                        # ATM swap rate
                        atm = calibrator._par_swap_rate_from_curve(calc_expiry, calc_tenor, 0.5)
                        K = calc_strike if calc_strike is not None else atm

                        price = calibrator.swaption_price(
                            calc_expiry, calc_tenor, K, 0.5, calc_option_type)
                        nvol = calibrator.swaption_normal_vol(calc_expiry, calc_tenor, K)
                        nvol_bps = nvol * 10000 if not np.isnan(nvol) else float("nan")

                        # Annuity
                        n_pay = max(1, int(round(calc_tenor / 0.5)))
                        annuity = sum(
                            0.5 * calibrator._P0(calc_expiry + (i + 1) * 0.5)
                            for i in range(n_pay)
                        )

                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("ATM Rate", f"{atm*100:.4f}%")
                        r2.metric("Swaption Price", f"{price:.8f}")
                        r3.metric("Normal Vol", f"{nvol_bps:.2f} bps")
                        r4.metric("Annuity", f"{annuity:.6f}")

                else:  # Cap
                    cc1, cc2 = st.columns(2)
                    calc_cap_mat = cc1.number_input(
                        "Cap Maturity (Y)", value=5.0, min_value=0.5, step=0.5, key="calc_cap_mat",
                    )
                    calc_cap_strike = cc2.number_input(
                        "Strike Rate (%)", value=3.0, format="%.4f", key="calc_cap_strike",
                    ) / 100.0

                    if st.button("계산", key="calc_cap_btn"):
                        cap_px = calibrator.cap_price(calc_cap_mat, calc_cap_strike, freq=0.25)
                        try:
                            cap_bvol = calibrator.cap_black_vol(calc_cap_mat, calc_cap_strike, freq=0.25)
                            cap_bvol_pct = cap_bvol * 100 if not np.isnan(cap_bvol) else float("nan")
                        except Exception:
                            cap_bvol_pct = float("nan")

                        r1, r2 = st.columns(2)
                        r1.metric("Cap Price", f"{cap_px:.8f}")
                        r2.metric("Black Vol", f"{cap_bvol_pct:.2f}%")

            except Exception as e:
                st.error(f"오류: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.info("왼쪽에서 시장 데이터를 입력하고 **Build Curve & Calibrate** 버튼을 누르세요.")
