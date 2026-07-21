# 📈 Interest Rate Curve Builder

시장 호가(스왑 금리·채권 수익률)로부터 **Zero Rate / Discount Factor / Forward Rate**를
추출하는 금리 커브 부트스트래핑 시스템입니다.

Streamlit 웹 UI에서 시장 데이터를 직접 입력하거나 Bloomberg 엑셀을 업로드해
커브를 빌드하고, 결과를 차트·테이블·CSV로 확인할 수 있습니다.

## 지원 커브

| 커브 | 클래스 | 시장 관례 | 입력 |
|---|---|---|---|
| 🇺🇸 USD SOFR IRS | `USDSOFRCurve` | Act/360, 고정 연 1회 지급 | SOFR O/N·3M + IRS 1Y~30Y |
| 🇰🇷 KRW CD IRS | `KRWCDCurve` | Act/365, 고정 분기(3M) 지급 | CD 91일 + IRS 6M~30Y |
| 🇰🇷 KRW KTB (국고채) | `KRWKTBCurve` | Act/365, 반기(6M) 쿠폰 | 3M·6M 단기채(단리) + 국고채 1Y~50Y |

## 핵심 방법론

- **부트스트랩**: 중간 테너 선형 보간 후 필라별 DF 순차 역산 → 입력 금리 재현 오차 **0 bps**
- **보간**: Hagan-West (2006) **Monotone Convex** — 선도금리 양수·경계 연속 보장
- **Densification**: 부트스트랩 후 0.25Y 간격 가상 노드 추가 (시장 필라 DF 정확 보존)
- **검증 4대 조건**: ① MC 보간 적용 ② Sawtooth 없음 ③ 적분 정합성 ④ No-Arbitrage
  (자세한 내용은 [docs/methodology.md](docs/methodology.md) 참고)

## 설치 및 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속.

### 사용 방법

1. **사이드바**: 저장소 샘플(`data/260721_Rates.xlsx`) 사용 또는 Bloomberg 엑셀 업로드
2. **기준일 선택**: 영업일 목록에서 선택 → 3개 탭 입력 테이블 자동 주입
3. **탭별 Build 버튼**: 커브 빌드 → Summary 테이블 / 차트 / Validation / CSV 다운로드
4. 입력 테이블은 자동 주입 후에도 **직접 수정 가능** (행 추가·삭제 포함)

### 예제 스크립트 (UI 없이 실행)

```bash
python examples/usd_sofr_example.py      # USD SOFR 커브 예제
python examples/krw_cd_example.py        # KRW CD IRS 커브 예제
python examples/krw_ktb_example.py       # KRW KTB 커브 예제
python examples/krw_ktb_validation.py    # 4대 검증 조건 수치 검증
```

## 폴더 구조

```
KIS_test/
├── app.py                      # Streamlit UI (3개 탭 + 엑셀 로더 사이드바)
├── requirements.txt
├── data/
│   └── 260721_Rates.xlsx       # 샘플 시장 데이터 (Bloomberg export)
├── curves/
│   ├── base_curve.py           # IRCurve 기반 클래스 (보간·densify·조회)
│   ├── usd_sofr_curve.py       # USD SOFR IRS 부트스트래퍼
│   ├── krw_cd_curve.py         # KRW CD IRS 부트스트래퍼
│   └── krw_ktb_curve.py        # KRW KTB(국고채) 부트스트래퍼
├── utils/
│   ├── day_count.py            # 테너 연산(1.5Y 지원)·Day Count
│   ├── interpolation.py        # Hagan-West Monotone Convex 보간
│   └── market_loader.py        # Bloomberg 엑셀 → 커브 입력 변환
├── examples/                   # 예제·검증 스크립트
└── docs/
    └── methodology.md          # 방법론 상세 문서
```

## 데이터 형식

`data/260721_Rates.xlsx` — Bloomberg 시계열 export 형식:
- R5: 테너 라벨 (`1y IRS`, `3m KTB`, `CD수익률` 등) / R6: Bloomberg 티커 / R9~: 일별 데이터
- 주말 행은 금요일 값 carry-forward → 로더가 자동 제거
- 금리 단위: % (예: 4.03 = 4.03%)

같은 형식이면 다른 날짜의 엑셀도 그대로 업로드해 사용할 수 있습니다.
