# 📈 Interest Rate Curve Builder

시장 호가(스왑 금리·채권 수익률)로부터 **Zero Rate / Discount Factor / Forward Rate**를
추출하는 금리 커브 부트스트래핑 시스템입니다.

Streamlit 웹 UI에서 시장 데이터를 직접 입력하거나 시장 금리 엑셀을 업로드해
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

1. **사이드바**: 시장 금리 엑셀 업로드 (데이터 파일은 저작권 이슈로 레포에 포함하지 않음)
2. **기준일 선택**: 영업일 목록에서 선택 → 3개 탭 입력 테이블 자동 주입
   → 아래 **🚀 전체 커브 일괄 빌드** 버튼으로 3개 커브를 한 번에 계산 가능 (탭별 Build 불필요)
3. **탭별 Build 버튼**: 커브 빌드 → KPI 카드(주요 테너 Zero·10Y−2Y 기울기, 전일 대비 Δbp)
   / 2단 차트(Zero·Fwd + DF, 화이트 배경) / No-Arbitrage 검증 배지 / Summary / CSV 다운로드
4. **📊 Compare 탭**: 빌드된 커브 Zero 오버레이 + IRS−KTB 스왑 스프레드 차트·테이블
5. 빌드 결과는 세션에 유지되어 탭 전환·입력 조작에도 사라지지 않음 (입력 변경 시 재빌드 경고)
6. 입력 테이블은 자동 주입 후에도 **직접 수정 가능**, 엑셀 없이 직접 입력만으로도 빌드 가능

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
├── app.py                      # Streamlit UI (3개 탭 + 엑셀 업로드 사이드바)
├── requirements.txt
├── curves/
│   ├── base_curve.py           # IRCurve 기반 클래스 (보간·densify·조회)
│   ├── usd_sofr_curve.py       # USD SOFR IRS 부트스트래퍼
│   ├── krw_cd_curve.py         # KRW CD IRS 부트스트래퍼
│   └── krw_ktb_curve.py        # KRW KTB(국고채) 부트스트래퍼
├── utils/
│   ├── day_count.py            # 테너 연산(1.5Y 지원)·Day Count
│   ├── interpolation.py        # Hagan-West Monotone Convex 보간
│   └── market_loader.py        # 시장 금리 엑셀 → 커브 입력 변환
├── examples/                   # 예제·검증 스크립트
└── docs/
    └── methodology.md          # 방법론 상세 문서
```

## 데이터 형식 (업로드용 엑셀)

> ⚠️ 시장 데이터 파일은 **저작권(데이터 라이선스) 이슈로 레포에 포함하지 않습니다.**
> 실행 시 화면에서 직접 업로드하세요 (`data/` 폴더는 .gitignore 처리됨).

시장 금리 시계열 엑셀 형식을 지원합니다:
- 필수 시트: 이름에 `SOFR IRS` / `KRW Rates(IRS)` / `KRW Treasury`를 포함하는 시트 (부분 일치 매칭)
- R5: 테너 라벨 (`1y IRS`, `3m KTB`, `CD수익률` 등) / R9~: 일별 데이터
- 주말 행은 금요일 값 carry-forward → 로더가 자동 제거
- 금리 단위: % (예: 4.03 = 4.03%)

같은 형식이면 어떤 날짜 범위의 엑셀도 업로드해 사용할 수 있습니다.
