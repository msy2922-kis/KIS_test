# CLAUDE.md — 개발 가이드

금리 커브 부트스트래핑 시스템 (USD SOFR IRS / KRW CD IRS / KRW KTB)
+ Short Rate 모델 시뮬레이션 + Hull-White 캘리브레이션.
프로젝트 개요는 [README.md](README.md), 방법론 상세는 [docs/methodology.md](docs/methodology.md),
시뮬레이션 구조는 [ARCHITECTURE.md](ARCHITECTURE.md) 참고.

## 서브 프로젝트 구성 (2026-07-27 브랜치 통합)

| 영역 | 진입점 | 핵심 모듈 | 출처 브랜치 |
|---|---|---|---|
| 커브 부트스트래핑 | `app.py` (Streamlit) | `curves/`, `utils/` | interest-rate-curve-extraction-OMELj |
| Short Rate 시뮬레이션 | `simulation_app.py` (Streamlit), `main.py` (CLI) | `short_rate_models.py`, `simulation.py`, `visualization.py` | add-documentation-2abHL (⊃ short-rate-simulation-CJMlz) |
| HW 캘리브레이션 | `examples/hw_calibration_example.py` | `calibration/hw_calibrator.py` | add-curve-fitting-calibration-7j4eh |

주의: 7j4eh 브랜치의 app.py(HW Calibration 탭 포함 구버전 UI)는 통합 시 채택하지 않았다.
HW 탭을 UI에 다시 넣으려면 현재 `app.py` 기준으로 새로 붙여야 한다.

## 아키텍처 요약

- `curves/base_curve.py` — `IRCurve` 기반 클래스. 모든 커브가 상속.
  - DF 저장(`_times`, `_dfs`) + Monotone Convex 보간 조회 (`zero_rate`, `discount_factor`, `forward_rate`)
  - `_densify(step=0.25)`: 부트스트랩 후 0.25Y 가상 노드 삽입 (시장 필라 DF 보존)
- `curves/usd_sofr_curve.py` / `krw_cd_curve.py` / `krw_ktb_curve.py` — 커브별 부트스트래퍼
  - 공통 패턴: 중간 테너 선형 보간 → 순차 부트스트랩 → `_densify()` 호출
- `utils/interpolation.py` — `monotone_convex_df()` (Hagan-West 2006). 커브 보간의 단일 진입점.
- `utils/day_count.py` — `add_tenor()` (소수 연도 `1.5Y` 지원), `tenor_to_years()`, `dcf()`
- `utils/market_loader.py` — 시장 금리 엑셀 파서. 시트 R5 라벨 → 표준 테너 정규화, 주말 필터.
- `app.py` — Streamlit UI. 사이드바 엑셀 **업로드 전용** 로더 → `market` 스냅샷 → 탭별 자동 주입.

### 데이터 정책 (중요)
시장 데이터 엑셀은 **저작권(데이터 라이선스) 이슈로 레포에 커밋 금지**.
`data/` 폴더는 .gitignore 처리되어 있으며, 사용자는 UI에서 그때그때 업로드한다.
샘플 파일을 레포에 추가하자는 요청이 와도 이 정책을 먼저 상기시킬 것.

## 필수 규칙

### 1. 커브 로직 수정 시 검증 필수
커브 클래스·보간·densify를 수정하면 **반드시** 아래를 실행해 4대 조건 통과를 확인:
```bash
python examples/krw_ktb_validation.py
```
- ① Monotone Convex (선도금리 양수 + 필라 경계 연속, 점프 < 0.01 bps)
- ② Sawtooth 없음
- ③ 적분 정합성 (오차 < 1e-6)
- ④ No-Arbitrage (입력 금리 역산 오차 < 0.5 bps — 실제로는 0 bps여야 정상)

3개 커브 모두 `par_swap_rate()` / `par_bond_yield()` 역산으로 입력 재현을 확인할 것.

### 2. 시장 관례 (변경 금지, 변경 시 사용자 확인)
| 커브 | Day Count | 고정 지급 주기 | 단기 앵커 |
|---|---|---|---|
| USD SOFR | ACT/360 | 연 1회 | OIS 단리 (sub-1Y) |
| KRW CD | ACT/365 | 분기(3M) | CD 91일 단리 |
| KRW KTB | ACT/365 | 반기(6M) | 3M·6M 단기채 단리 |

### 3. 문서 동기화
코드·구조를 수정하면 관련 문서(README.md, CLAUDE.md, docs/methodology.md)도 같은 커밋에서 갱신할 것.

### 4. Git
- 개발 브랜치: `main` (2026-07-27에 claude/* 작업 브랜치들을 통합 완료)
- 커밋 메시지는 한국어 본문 허용, 접두사(feat/fix/test/docs) 사용
- push 전 예제 스크립트로 스모크 테스트

## 주의사항 (과거에 실제 발생한 이슈)

- **테너 파싱**: `add_tenor()`는 `1.5Y`(→18M) 같은 소수 연도를 지원한다. 새 테너 형식 추가 시 `tenor_to_years()`도 함께 갱신.
- **UI 차트**: `curve_figure()`는 300pt 고밀도 그리드 + 2단 서브플롯(화이트 배경). 희소 테너로 직접 그리면 꺾임 발생 — 하지 말 것. 화이트 배경 유지를 위해 `st.plotly_chart(..., theme=None)` 필수.
- **빌드 결과 보존**: 커브는 `st.session_state["curves"]`에 저장되어 rerun에도 유지. Build 시 입력 시그니처(`_sig`)도 함께 저장해 stale 입력 경고에 사용.
- **Streamlit data_editor**: 자동 주입 데이터가 바뀌면 위젯 key도 바뀌어야 테이블이 갱신됨 (`key=f"..._{mkey}"` 패턴 유지).
- **엑셀 데이터**: 주말 행은 carry-forward이므로 반드시 영업일 필터(`weekday < 5`) 적용.
- **`_fill_*_tenors` 사전 보간**: quoted tenor 사이를 채우지 않으면 중간 지급일 flat-extrapolation으로 역산 오차 발생 (5Y+ 테너에서 수 bps).

## 실행 명령

```bash
pip install -r requirements.txt
streamlit run app.py                        # 커브 빌더 UI
streamlit run simulation_app.py             # Short Rate 3D 시뮬레이션 UI
python main.py                              # 시뮬레이션 CLI 데모 (PNG 저장)
python examples/krw_ktb_validation.py       # 4대 조건 검증
python examples/hw_calibration_example.py   # HW 캘리브레이션 예제
```
