# 금리 커브 부트스트래핑 방법론

본 문서는 커브 세팅의 수식·가정·검증 기준을 기록한다.
코드 변경으로 방법론이 바뀌면 이 문서를 같은 커밋에서 갱신한다.

---

## 1. 커브별 시장 관례

| 항목 | USD SOFR IRS | KRW CD IRS | KRW KTB (국고채) |
|---|---|---|---|
| 대상 상품 | SOFR OIS 스왑 | CD금리 스왑 | 국고채 현물 (민평 수익률) |
| Day Count | ACT/360 | ACT/365 Fixed | ACT/365 Fixed |
| 고정레그/쿠폰 주기 | 연 1회 | 분기 (3M) | 반기 (6M) |
| 단기 앵커 | OIS 예금금리 (sub-1Y, 단리) | CD 91일물 (단리) | 3M·6M 단기채 (단리) |
| 장기 구간 | IRS par rate 1Y~30Y | IRS par rate 6M~30Y | 국고채 par yield 1Y~50Y |
| 영업일 조정 | 미적용 (단순화) | 미적용 | 미적용 |

단기 앵커의 할인인수: `DF = 1 / (1 + r·τ)` (단리, τ는 해당 컨벤션의 day count fraction)

## 2. 부트스트랩

### 2.1 Par 조건 (스왑·채권 공통 수식)

고정레그 지급일 {T₁,…,T_N}, 구간 dcf τᵢ, par rate(또는 par yield) R:

```
DF(T_N) = (1 − R·Σᵢ₌₁ᴺ⁻¹ τᵢ·DF(Tᵢ)) / (1 + R·τ_N)
```

- IRS: 고정레그 PV = 변동레그 PV(= 1 − DF(T_N), par floater 근사)
- KTB: 쿠폰 annuity + 원금 DF = 액면가 — 수학적으로 동일한 식

### 2.2 중간 테너 사전 보간 (필수)

Quoted tenor 사이의 모든 지급 주기 테너(USD 1Y, CD 3M, KTB 6M 간격)를
par rate **선형 보간**으로 채운 뒤 짧은 만기부터 순차 부트스트랩한다.

> 이유: 5Y 스왑 부트스트랩 시 4Y 지급일이 필라에 없으면 flat extrapolation으로
> 수 bps의 역산 오차가 발생한다. 사전 보간으로 모든 지급일이 정확한 필라가 된다.

### 2.3 Densification (0.25Y 가상 노드)

부트스트랩 완료 후 `IRCurve._densify(step=0.25)`:
1. 0.25Y 간격 가상 노드를 현재 MC 커브로 평가해 삽입
2. 시장 필라와 tol(=step×2%) 이내 중복 노드는 생략
3. 시장 필라 DF는 정확히 보존 → No-Arbitrage 유지

## 3. 보간: Hagan-West (2006) Monotone Convex

`utils/interpolation.py :: monotone_convex_df()`

1. 이산 선도금리: `fᵢ = −Δln(DF)/Δt`
2. 필라 순간 선도금리: `gᵢ` = 인접 구간 길이 가중 평균
3. 단조성 제약: 부호 전환 시 `gᵢ = 0`, 동일 부호 시 `2·min(|fᵢ|,|fᵢ₊₁|)` 클램핑
4. 구간 내 2차 보간 (정규화 좌표 x∈[0,1]):
   `g(x) = gᵢ + (6f−4gᵢ−2gᵢ₊₁)x + (3gᵢ+3gᵢ₊₁−6f)x²` — `∫₀¹g dx = fᵢ` (면적 보존)
5. `ln DF(t) = ln DF(tᵢ) − hᵢ·∫₀ˣ g dy` 로 DF 복원

외삽: 좌측 DF 고정, 우측 마지막 이산 선도금리로 flat-forward.

### Log-Linear를 쓰지 않는 이유
Log-Linear DF(=구간별 선형 zero)는 구간 내 선도금리가 상수여서 필라 경계에서
불연속(sawtooth) 발생. MC는 경계 연속·양수 선도금리·면적 보존을 동시 보장.

## 4. 산출물 정의

- **Zero Rate**: 연속복리 `z(t) = −ln DF(t) / t` (UI·summary 기본)
- **Discount Factor**: `P(0,t)`
- **3M Forward Rate**: 단리 `f(t, t+0.25) = (DF(t)/DF(t+0.25) − 1) / 0.25`

## 5. 검증 기준 (4대 조건)

`examples/krw_ktb_validation.py` — 커브 로직 수정 시 필수 실행.

| # | 조건 | 판정 기준 | 최근 결과 |
|---|---|---|---|
| 1-A | 순간 선도금리 양수 | 음수 0건 | PASS (최솟값 2.81%) |
| 1-B | 선도금리 필라 경계 연속 | 점프 < 0.01 bps | PASS (0.0003 bps) |
| 2 | Sawtooth 없음 | 경계 점프 < 0.01 bps | PASS (0.000342 bps) |
| 3 | 적분 정합성 | ∣∫g dt − (−ln DF비)∣ < 1e-6 | PASS (~1e-9) |
| 4 | No-Arbitrage | 입력 금리 역산 오차 ≈ 0 bps | PASS (0.000000 bps) |

## 6. 데이터 소스

`data/260721_Rates.xlsx` — Bloomberg 시계열 export (2023-01-01 ~ 2026-07-21):

| 시트 | 사용 | 내용 |
|---|---|---|
| SOFR IRS(BGN cut) | ✅ | USOSFR1~30 + SOFRRATE(O/N) + XSOFR3M(3M 복리) |
| KRW Rates(IRS) | ✅ | KWSWO 6M~30Y (1.5Y·4Y 포함) + KWCDC(CD) |
| KRW Treasury | ✅ | KBGBG(민평4사) 3M~50Y + KWCDC |
| US Treasury / KRW Rates(CRS) / USDKRW | 미사용 | 향후 UST·CRS·FX-implied 커브 확장용 |

로더(`utils/market_loader.py`) 처리: 주말 carry-forward 행 제거, `'1y IRS'→'1Y'` 정규화,
% 단위 유지(커브 생성 시 /100).

## 7. 알려진 단순화 (향후 개선 후보)

- 영업일 조정(Modified Following 등) 및 휴일 캘린더 미적용
- USD SOFR 변동레그를 par floater로 근사 (일별 복리 정밀 계산 아님)
- KTB 쿠폰을 par yield 기반 이론 채권으로 근사 (실제 종목별 쿠폰/경과이자 미반영)
- 결제일(T+1/T+2) 스팟 랙 미적용
