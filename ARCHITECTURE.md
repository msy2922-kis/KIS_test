# KIS_test 프로젝트 아키텍처 문서

## 1. 프로젝트 개요

단기금리(Short Rate) 모델 기반 금리 시뮬레이션 및 3D 수익률 곡면 시각화 프로젝트.

네 가지 고전 단기금리 모델(Vasicek, CIR, Hull-White, Ho-Lee)을 Monte Carlo 시뮬레이션으로 구동하고,
부트스트랩된 실제 시장 커브(KRW 국고채, KRW CD IRS, USD SOFR IRS)와 연동하여
Three.js 기반 3D 수익률 곡면을 Streamlit 웹앱으로 시각화한다.

---

## 2. 디렉토리 구조

```
KIS_test/
├── app.py                      # Streamlit 웹앱 (3D 시각화 메인)
├── main.py                     # CLI 데모 스크립트
├── short_rate_models.py        # 단기금리 모델 정의 (4개 모델)
├── simulation.py               # Monte Carlo 시뮬레이션 엔진
├── visualization.py            # Matplotlib 시각화 유틸리티
├── requirements.txt            # Python 패키지 의존성
├── curves/                     # 금리 커브 부트스트래핑 모듈
│   ├── __init__.py
│   ├── base_curve.py           # IRCurve 추상 베이스 클래스
│   ├── krw_ktb_curve.py        # KRW 국고채 커브
│   ├── krw_cd_curve.py         # KRW CD IRS 커브
│   └── usd_sofr_curve.py       # USD SOFR IRS 커브
├── utils/                      # 유틸리티 모듈
│   ├── __init__.py
│   ├── day_count.py            # Day Count Convention 함수
│   └── interpolation.py        # 보간법 (Monotone Convex 등)
└── *.png                       # 시뮬레이션 결과 이미지 파일들
```

---

## 3. 클래스 계층 구조

```
ShortRateModel (ABC)               # 단기금리 모델 추상 베이스
├── VasicekModel                   # Vasicek (1977)
├── CIRModel                      # Cox-Ingersoll-Ross (1985)
├── HullWhiteModel                # Hull-White (1990) - 확장 Vasicek
└── HoLeeModel                    # Ho-Lee (1986)

IRCurve                            # 금리 커브 베이스 클래스
├── KRWKTBCurve                   # KRW 국고채 커브
├── KRWCDCurve                    # KRW CD IRS 커브
└── USDSOFRCurve                  # USD SOFR IRS 커브

MonteCarloSimulator                # MC 시뮬레이션 엔진 (독립 클래스)
```

---

## 4. 파일별 상세 설명

### 4.1 `short_rate_models.py` — 단기금리 모델 정의

네 가지 고전 단기금리 모델을 구현한 핵심 모듈.

#### 헬퍼 함수

| 함수 | 설명 |
|------|------|
| `_make_fwd_from_ir_curve(curve)` | `IRCurve` 객체로부터 순간선도금리 callable `f^M(0,t)`을 생성 |

#### `ShortRateModel` (추상 베이스 클래스)

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `step()` | `(r, dt, dW) -> np.ndarray` | 한 시간 스텝 전진 (추상) |
| `name` | `@property -> str` | 모델 이름 (추상) |

#### `VasicekModel`

- **SDE**: `dr_t = κ(θ - r_t)dt + σdW_t`
- **이산화**: Exact (non-Euler) discretization 사용

| 파라미터 | 설명 |
|---------|------|
| `kappa` | 평균 회귀 속도 (κ > 0) |
| `theta` | 장기 평균 금리 (θ) |
| `sigma` | 변동성 (σ > 0) |
| `r0` | 초기 단기금리 |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `step()` | `(r, dt, dW) -> np.ndarray` | Exact discretization으로 금리 전진 |
| `theoretical_mean()` | `(t) -> float` | 이론적 조건부 기대값 `E[r_t\|r_0]` |
| `theoretical_variance()` | `(t) -> float` | 이론적 조건부 분산 `Var[r_t\|r_0]` |
| `bond_price_analytical()` | `(r, t, T) -> float` | 해석적 제로쿠폰채 가격 `P(t,T)` |

#### `CIRModel`

- **SDE**: `dr_t = κ(θ - r_t)dt + σ√(r_t)dW_t`
- **이산화**: Euler-Maruyama with full truncation (비음 보장)
- **Feller 조건**: `2κθ > σ²` 위반 시 경고 발생

| 파라미터 | 설명 |
|---------|------|
| `kappa` | 평균 회귀 속도 (κ > 0) |
| `theta` | 장기 평균 금리 (θ > 0) |
| `sigma` | 변동성 (σ > 0) |
| `r0` | 초기 단기금리 (≥ 0) |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `step()` | `(r, dt, dW) -> np.ndarray` | Euler-Maruyama + truncation |
| `theoretical_mean()` | `(t) -> float` | 이론적 기대값 |
| `theoretical_variance()` | `(t) -> float` | 이론적 분산 |
| `bond_price_analytical()` | `(r, t, T) -> float` | 해석적 채권 가격 (감마함수 기반) |

#### `HullWhiteModel`

- **SDE**: `dr_t = [θ(t) - κr_t]dt + σdW_t`
- **θ(t)**: 초기 순간선도금리 커브에 calibration되는 시간의존 드리프트
- **초기 커브**: `callable`, `IRCurve` 객체, 또는 `None` (flat) 지원

| 파라미터 | 설명 |
|---------|------|
| `kappa` | 평균 회귀 속도 |
| `sigma` | 변동성 |
| `r0` | 초기 단기금리 |
| `initial_curve` | 초기 선도금리 커브 (callable / IRCurve / None) |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_theta()` | `(t, eps) -> float` | θ(t) 계산: `∂f/∂t + κf(t) + σ²/(2κ)(1-e^{-2κt})` |
| `step()` | `(r, dt, dW) -> np.ndarray` | 기본 스텝 (t=0 가정) |
| `step_at()` | `(r, dt, dW, t) -> np.ndarray` | 시간 인식 스텝 (시뮬레이션용) |
| `_log_P0()` | `(t) -> float` | `ln P^M(0,t)` — IRCurve DF 또는 수치적분 |
| `bond_price_analytical()` | `(r, t, T) -> float/ndarray` | `P(t,T) = exp(A - B·r_t)` |

#### `HoLeeModel`

- **SDE**: `dr_t = θ(t)dt + σdW_t`
- **θ(t)**: `∂f(0,t)/∂t + σ²t`
- 평균 회귀 없음 (κ=0의 Hull-White 특수 케이스)

| 파라미터 | 설명 |
|---------|------|
| `sigma` | 변동성 |
| `r0` | 초기 단기금리 |
| `initial_curve` | 초기 선도금리 커브 |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_theta()` | `(t, eps) -> float` | θ(t) = ∂f/∂t + σ²t |
| `step()` | `(r, dt, dW) -> np.ndarray` | 기본 스텝 |
| `step_at()` | `(r, dt, dW, t) -> np.ndarray` | 시간 인식 스텝 |
| `_log_P0()` | `(t) -> float` | `ln P^M(0,t)` |
| `bond_price_analytical()` | `(r, t, T) -> float/ndarray` | `P(t,T) = exp(A - τ·r_t)` |

---

### 4.2 `simulation.py` — Monte Carlo 시뮬레이션 엔진

#### `MonteCarloSimulator`

`ShortRateModel` 인스턴스를 받아 Monte Carlo 경로를 생성하고 통계를 계산하는 범용 시뮬레이션 엔진.

| 파라미터 | 설명 |
|---------|------|
| `model` | `ShortRateModel` 서브클래스 인스턴스 |
| `seed` | 난수 시드 (재현성 보장) |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `simulate()` | `(T, n_steps, n_paths) -> (times, paths)` | MC 경로 생성. `step_at()` 존재 시 시간 인식 모드 자동 전환 |
| `compute_statistics()` | `(paths, percentiles) -> dict` | 시간별 기술통계 (평균, 표준편차, 백분위수) |
| `bond_price()` | `(paths, dt) -> float` | MC 기반 제로쿠폰채 가격 `P(0,T) ≈ E[exp(-∫r dt)]` (사다리꼴 적분) |
| `term_structure()` | `(maturities, n_steps_per_year, n_paths) -> np.ndarray` | MC 기반 제로쿠폰 수익률 곡선 계산 |
| `print_summary()` | `(times, paths) -> None` | 시뮬레이션 결과 콘솔 요약 출력 |

---

### 4.3 `visualization.py` — Matplotlib 시각화 유틸리티

CLI 데모(`main.py`)용 정적 차트 생성 모듈.

| 상수 | 설명 |
|------|------|
| `MODEL_COLORS` | 모델별 색상 맵 (Vasicek: 파랑, CIR: 초록, HW: 주황, HL: 보라) |

| 함수 | 시그니처 | 설명 |
|------|---------|------|
| `plot_paths()` | `(times, paths, model_name, n_display, save_path) -> Figure` | 개별 경로 + 평균 + 백분위 밴드 차트 |
| `plot_distribution()` | `(paths, times, t_indices, model_name, save_path) -> Figure` | 특정 시점의 금리 분포 히스토그램 (기본: 4개 시점) |
| `plot_term_structure()` | `(maturities, yields, model_name, initial_curve, save_path) -> Figure` | MC 기반 수익률 곡선 vs 초기 선도금리 비교 차트 |
| `compare_models()` | `(results, save_path) -> Figure` | 모델 간 비교 차트 (평균 경로 + 만기 분포) |

---

### 4.4 `curves/base_curve.py` — IRCurve 베이스 클래스

모든 부트스트랩 커브의 베이스 클래스. 할인인수를 저장하고 제로금리, 선도금리를 유도한다.

#### `IRCurve`

| 내부 상태 | 설명 |
|----------|------|
| `_times` | 필라 시간(year fraction) 배열 — 정렬됨, `[0]`은 0.0 |
| `_dfs` | 필라 할인인수 배열 — `[0]`은 1.0 |
| `valuation_date` | 기준일 |
| `name` | 커브 이름 |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_set_pillars()` | `(times, dfs) -> None` | 부트스트랩된 필라 시간/DF 저장 (내부 빌더용) |
| `_densify()` | `(step=0.25) -> None` | 0.25Y 간격 가상 노드 추가 — MC 보간 정밀도 향상 |
| `discount_factor()` | `(t) -> np.ndarray` | Monotone Convex 보간 할인인수 `P(0,t)` |
| `zero_rate()` | `(t, compounding) -> np.ndarray` | 제로금리 (continuous/simple/annual 복리) |
| `forward_rate()` | `(t1, t2, compounding) -> np.ndarray` | 선도금리 `f(t1, t2)` |
| `summary()` | `(tenors_yr) -> pd.DataFrame` | 주요 테너 요약 테이블 |

---

### 4.5 `curves/krw_ktb_curve.py` — KRW 국고채 커브

#### `KRWKTBCurve` (extends `IRCurve`)

한국 국고채(KTB) 파 수익률로부터 제로커브를 부트스트랩한다.

**시장 컨벤션**:
- Day Count: ACT/365 Fixed
- 쿠폰: 반기 (6개월 간격)
- Short End: 3M/6M 단리

| 파라미터 | 설명 |
|---------|------|
| `valuation_date` | 기준일 |
| `bond_quotes` | 국고채 파 수익률 딕셔너리 (예: `{'1Y': 0.033, '10Y': 0.035}`) |
| `short_rate_3m` | 3M 단리 금리 (선택) |
| `short_rate_6m` | 6M 단리 금리 (선택) |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_bootstrap()` | `() -> None` | Short End 단리 DF + 반기 쿠폰 채권 순차 부트스트랩 |
| `par_bond_yield()` | `(tenor) -> float` | 커브 내재 파 수익률 (검증용) |
| `par_swap_rate()` | `(tenor) -> float` | `par_bond_yield()` 별칭 |

#### 모듈 헬퍼 함수

| 함수 | 설명 |
|------|------|
| `_semiannual_schedule(valuation, maturity)` | 반기 지급일 스케줄 생성 |
| `_fill_semiannual_tenors(bond_quotes, valuation, short_quotes)` | 누락된 6M 단위 테너를 선형 보간으로 보충 |

---

### 4.6 `curves/krw_cd_curve.py` — KRW CD IRS 커브

#### `KRWCDCurve` (extends `IRCurve`)

CD 91일물 예금금리 + CD IRS 고정금리로부터 제로커브를 부트스트랩한다.

**시장 컨벤션**:
- Day Count: ACT/365 Fixed
- 고정레그: 분기 지급 (3M 간격)
- 변동레그: 91일 CD금리 분기 리셋

| 파라미터 | 설명 |
|---------|------|
| `valuation_date` | 기준일 |
| `cd_rate` | 91일 CD 금리 (소수 표기) |
| `swap_quotes` | CD IRS 고정금리 딕셔너리 |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_bootstrap()` | `() -> None` | 분기 단위 순차 부트스트랩 |
| `par_swap_rate()` | `(tenor) -> float` | 커브 내재 파 스왑레이트 (검증용) |

#### 모듈 헬퍼 함수

| 함수 | 설명 |
|------|------|
| `_quarterly_schedule(valuation, maturity)` | 분기 지급일 스케줄 생성 |
| `_fill_quarterly_tenors(cd_rate, swap_quotes, valuation)` | 누락된 3M 단위 테너를 선형 보간으로 보충 |

---

### 4.7 `curves/usd_sofr_curve.py` — USD SOFR IRS 커브

#### `USDSOFRCurve` (extends `IRCurve`)

SOFR OIS 단기금리 + SOFR IRS 파 고정금리로부터 제로커브를 부트스트랩한다.

**시장 컨벤션**:
- Day Count: ACT/360
- 고정레그: 연간 지급
- 변동레그: 일간복리 SOFR

| 파라미터 | 설명 |
|---------|------|
| `valuation_date` | 기준일 |
| `ois_quotes` | OIS 단기 금리 딕셔너리 (1Y 이하) |
| `swap_quotes` | SOFR IRS 고정금리 딕셔너리 (1Y 초과) |

| 메서드 | 시그니처 | 설명 |
|--------|---------|------|
| `_bootstrap()` | `() -> None` | OIS 단리 DF → 연간 스왑 순차 부트스트랩 |
| `par_swap_rate()` | `(tenor) -> float` | 커브 내재 파 스왑레이트 (검증용) |

#### 모듈 헬퍼 함수

| 함수 | 설명 |
|------|------|
| `_annual_schedule(valuation, maturity)` | 연간 지급일 스케줄 생성 |
| `_fill_annual_tenors(ois_quotes, swap_quotes, valuation)` | 누락된 정수년 테너를 선형 보간으로 보충 |

---

### 4.8 `utils/day_count.py` — Day Count Convention

금리 계산에 필요한 날짜 계산 유틸리티.

| 함수 | 시그니처 | 설명 |
|------|---------|------|
| `add_tenor()` | `(base_date, tenor) -> date` | 테너 문자열을 날짜에 가산 (D/W/M/Y 지원) |
| `act360()` | `(start, end) -> float` | Actual/360 day count fraction |
| `act365()` | `(start, end) -> float` | Actual/365 Fixed day count fraction |
| `dcf()` | `(start, end, convention) -> float` | 컨벤션별 day count fraction 디스패처 |

---

### 4.9 `utils/interpolation.py` — 보간법

금리 커브 보간에 사용되는 수학 함수들.

| 함수 | 시그니처 | 설명 |
|------|---------|------|
| `linear_interp()` | `(x_known, y_known, x_query) -> np.ndarray` | 선형 보간 + 평탄 외삽 |
| `log_linear_df()` | `(t_known, df_known, t_query) -> np.ndarray` | 로그-선형 할인인수 보간 (선형 제로금리 등가) |
| `monotone_convex_df()` | `(t_known, df_known, t_query) -> np.ndarray` | **Monotone Convex** 보간 (Hagan & West, 2006) |

**Monotone Convex 보간의 4대 보장 속성**:
1. 순간 선도금리 양수 유지
2. 선도금리 연속 (필라 경계 점프 없음)
3. 적분 정합성 보존
4. 필라 정확 통과

---

### 4.10 `app.py` — Streamlit 3D 시각화 웹앱

전체 시스템의 프론트엔드. Streamlit + Three.js로 인터랙티브 3D 수익률 곡면을 렌더링한다.

#### 주요 구성 요소

| 섹션 | 설명 |
|------|------|
| **Sidebar** | 모델 선택, 파라미터 슬라이더, 시뮬레이션 설정, 비주얼 스타일, 초기 커브 선택 |
| **Curve Builder** | Hull-White/Ho-Lee 모델의 시장 커브 입력 UI (국고채, CD IRS, SOFR IRS) |
| **3D Surface** | Three.js 기반 3D 수익률 곡면 (마우스 드래그/줌/호버 툴팁) |
| **Rate Paths** | Matplotlib 2D 시뮬레이션 경로 차트 |
| **Model Details** | 수학 공식 및 파라미터 표시 |

#### 주요 함수

| 함수 | 설명 |
|------|------|
| `build_initial_curve(curve_source, val_date)` | 커브 소스별 UI 렌더링 + IRCurve 객체 생성, `(curve, r0)` 반환 |
| `run_simulation(...)` | 모델 생성 → MC 시뮬레이션 → 수익률 곡면 데이터 계산 |
| `build_threejs_html(data, config)` | Three.js HTML/JS 코드 생성 (Surface mesh, 축, 파티클, 조명, 애니메이션) |

#### Three.js 3D 시각화 기능
- **Yield Surface**: 정점 컬러 매핑 (Low→Mid→High)
- **축 시스템**: Time(t), Maturity(τ), Yield(%) — 색상 구분 (시안, 핑크, 골드)
- **인터랙션**: OrbitControls (회전/줌), Raycaster (호버 툴팁)
- **애니메이션**: 파티클 부유, Surface 호흡 효과, 조명 맥동
- **컬러 스킴**: Antigravity Neon / Thermal / Ocean / Monochrome

---

### 4.11 `main.py` — CLI 데모 스크립트

`python main.py`로 실행하는 커맨드라인 데모. 네 모델 모두를 순차 시뮬레이션하고 PNG 차트를 저장한다.

**실행 흐름**:
1. Vasicek 시뮬레이션 → 이론값 vs MC 비교 → 경로/분포 차트 저장
2. CIR 시뮬레이션 → 이론값 비교 → 차트 저장
3. Hull-White 시뮬레이션 → 경로/분포/기간구조 차트 저장
4. Ho-Lee 시뮬레이션 → 차트 저장
5. 4개 모델 비교 차트 저장 + 채권 가격 비교

**기본 설정**: T=5Y, N_PATHS=2000, daily step, r0=3%, κ=0.3, θ=5%, σ=1.5%

---

## 5. 데이터 흐름

```
┌─────────────────┐     ┌──────────────────┐
│  Market Quotes  │────>│  IRCurve 서브클래스 │  (부트스트랩)
│  (KTB/CD/SOFR)  │     │  KRWKTBCurve 등    │
└─────────────────┘     └────────┬─────────┘
                                 │ forward_rate(), discount_factor()
                                 v
┌─────────────────┐     ┌──────────────────┐
│  Model Params   │────>│  ShortRateModel   │  (θ(t) calibration)
│  (κ, θ, σ, r0)  │     │  HullWhite 등     │
└─────────────────┘     └────────┬─────────┘
                                 │ step_at(r, dt, dW, t)
                                 v
                        ┌──────────────────┐
                        │ MonteCarloSimulator│  (경로 생성)
                        │ simulate()        │
                        └────────┬─────────┘
                                 │ times, paths
                                 v
              ┌──────────────────────────────────┐
              │          Yield Surface 계산        │
              │  P(t,T) = bond_price_analytical() │
              │  y = -ln(P)/τ                     │
              └──────────┬───────────────────────┘
                         │ surface data
                         v
          ┌──────────────────────────────┐
          │     Visualization Layer       │
          │  Three.js 3D (app.py)        │
          │  Matplotlib 2D (visualization.py) │
          └──────────────────────────────┘
```

---

## 6. 핵심 알고리즘 요약

### 6.1 부트스트래핑
- **Short End**: 단리 할인인수 `DF = 1/(1 + r·t)`
- **Long End**: 파 수익률에서 순차적으로 DF 역산: `DF_N = (1 - c·PV01) / (1 + c·τ_N)`
- **보간**: 시장 필라 사이를 Monotone Convex로 보간 (무차익, 선도금리 연속)
- **Densify**: 부트스트랩 후 0.25Y 간격 가상 노드 추가로 보간 정밀도 향상

### 6.2 Monte Carlo 시뮬레이션
- Brownian increment: `dW ~ N(0, √dt)`
- 시간 인식 모델(HW, HL)은 `step_at(r, dt, dW, t)` 사용
- 수익률 곡면: 각 시간·만기 그리드 포인트에서 경로별 `P(t,T|r_t)` 계산 후 평균

### 6.3 해석적 채권 가격
- **Vasicek/CIR**: `P(t,T) = exp(A(t,T) - B(t,T)·r_t)` (Affine Term Structure)
- **Hull-White**: `B = (1-e^{-κτ})/κ`, A는 초기 커브의 `P^M(0,t)`, `f^M(0,t)` 사용
- **Ho-Lee**: `B = τ`, A는 초기 커브 기반

---

## 7. 의존성

| 패키지 | 버전 | 용도 |
|--------|------|------|
| numpy | ≥1.24.0 | 수치 계산 |
| scipy | ≥1.10.0 | 보간 (interp1d) |
| pandas | ≥2.0.0 | 데이터 프레임 |
| matplotlib | ≥3.7.0 | 2D 차트 |
| streamlit | ≥1.32.0 | 웹앱 프레임워크 |
| plotly | ≥5.20.0 | 인터랙티브 차트 |
| python-dateutil | ≥2.8.0 | 날짜 연산 (relativedelta) |
