# 단일 종목 분석 시스템

AI 기반 단일 종목 심층 분석 시스템입니다. 포트폴리오 분석 시스템의 구조를 참고하여 제작되었습니다.

## 📋 주요 기능

- **종합 분석**: 재무제표, 기술적 지표, 뉴스 감성을 종합한 AI 분석
- **DB 기반**: PostgreSQL에서 데이터를 효율적으로 조회
- **실시간 데이터**: yfinance와 Qdrant를 통한 최신 정보 반영
- **다양한 모델 지원**: GPT-4O, Claude 3.5 등 여러 LLM 선택 가능
- **직관적 UI**: 종목 선택 드롭다운 + 직접 입력 지원

## 🗂️ 파일 구조

```
agent_test/
  stock_analyzer_agent.py       # 핵심 분석 로직 (Tool Use 패턴)

experiments/
  stock_endpoint.py              # FastAPI 서버 (포트 8001)
  templates/stock/
    stock_analysis.html          # 프론트엔드 UI
    stock_analysis.css           # 스타일링
    stock_analysis.js            # 프론트엔드 로직

jobs/
  seed_companies.py              # 종목 마스터 데이터
  load_prices_daily.py           # 주가 데이터 로드
  load_fundamentals.py           # 재무 데이터 로드
  calc_signals_latest.py         # 기술적 지표 계산

test_stock_analyzer.py           # 테스트 스크립트
setup_stock_analyzer.py          # 자동 설정 스크립트
```

## 🚀 빠른 시작

### 1. 데이터베이스 설정

자동 설정 스크립트 실행:
```powershell
python setup_stock_analyzer.py
```

또는 수동으로 단계별 실행:
```powershell
# 1. 종목 마스터 데이터
python jobs/seed_companies.py

# 2. 주가 데이터 (5-10분 소요)
python jobs/load_prices_daily.py

# 3. 재무 데이터 (3-5분 소요)
python jobs/load_fundamentals.py

# 4. 기술적 지표 계산
python jobs/calc_signals_latest.py
```

### 2. 테스트

개별 Tool 테스트:
```powershell
python test_stock_analyzer.py tools
```

전체 분석 테스트:
```powershell
python test_stock_analyzer.py full
```

### 3. 웹 서버 실행

```powershell
cd experiments
uvicorn stock_endpoint:app --port 8001 --reload
```

브라우저에서 http://localhost:8001 접속

## 📊 데이터베이스 스키마

### companies (종목 마스터)
```sql
ticker (PK)     # 종목 코드 (예: 005930.KS)
krx_code        # KRX 코드
name_kr         # 종목명
market          # KOSPI/KOSDAQ
industry        # 산업 코드 (SEMI, BIO, AI 등)
is_active       # 활성 여부
```

### prices_daily (일별 주가)
```sql
ticker, date (PK)
open, high, low, close, adj_close
volume
```

### fundamentals (재무제표)
```sql
ticker, fiscal_date, freq (PK)
revenue, op_income, net_income
total_assets, total_liab, equity
ebitda, cash_from_ops, capex
```

### fin_metrics (재무 지표)
```sql
ticker, fiscal_date, freq (PK)
roe, opm, debt_ratio, roa
rev_growth_yoy, fcf
```

### signals_latest (기술적 지표)
```sql
ticker (PK)
asof, ma20, ma60
rsi14, atr14
momentum_20d, vol_20d
```

## 🔧 Tool 설명

### 1. get_stock_prices
- **데이터 소스**: `prices_daily` 테이블
- **반환 데이터**: 현재가, 수익률(1m/3m/6m), 변동성

### 2. get_financial_metrics
- **데이터 소스**: `fundamentals` + `fin_metrics` 테이블
- **반환 데이터**: 매출, 영업이익, ROE, 부채비율, FCF 등

### 3. get_technical_signals
- **데이터 소스**: `signals_latest` 테이블
- **반환 데이터**: RSI, 이동평균선, 추세, 지지/저항 구간

### 4. get_news_sentiment
- **데이터 소스**: Qdrant Vector DB (agents/tools.py)
- **반환 데이터**: 최근 뉴스, 감성 분석 결과

## 📋 출력 형식

완전한 JSON 구조로 반환:

```json
{
  "meta": {
    "generated_at": "2025-11-14T10:30:00",
    "model": "gpt-4o-mini",
    "profile": "balanced"
  },
  "basic_info": {
    "ticker": "005930.KS",
    "name_kr": "삼성전자",
    "market": "KOSPI",
    "industry": "반도체"
  },
  "market_snapshot": { ... },
  "financial_summary": { ... },
  "quality_scores": {
    "financial_score": 85,
    "technical_score": 72,
    "news_score": 68,
    "overall_score": 75
  },
  "technical_analysis": { ... },
  "news_and_momentum": { ... },
  "scenarios_1y": {
    "bull_case": { ... },
    "base_case": { ... },
    "bear_case": { ... }
  },
  "risks": { ... },
  "investment_thesis": { ... },
  "recommendation": {
    "rating": "BUY/HOLD/SELL",
    "target_price_range": "88,000 ~ 92,000",
    "confidence_level": "high/medium/low"
  }
}
```

## 🎯 주요 차이점: 포트폴리오 vs 단일 종목

| 구분 | 포트폴리오 분석 | 단일 종목 분석 |
|------|----------------|---------------|
| 입력 | 복수 종목 + 예산 | 단일 종목 |
| 출력 | 포트폴리오 구성 | 투자 의견 + 목표가 |
| 분석 깊이 | 섹터/상관관계 중심 | 개별 종목 심층 분석 |
| 시나리오 | 포트폴리오 전체 | 종목별 강세/기본/약세 |

## 🐛 트러블슈팅

### "No data available in DB"
→ `python jobs/load_prices_daily.py` 실행

### "No fundamental data available"
→ `python jobs/load_fundamentals.py` 실행

### "No technical signals available"
→ `python jobs/calc_signals_latest.py` 실행

### DB 연결 오류
→ `.env` 파일의 DB_HOST, DB_NAME, DB_USER, DB_PASS 확인

### yfinance 인증서 오류
→ `python experiments/fix_cert_path.py` 실행

## 📝 API 엔드포인트

- `GET /` - 메인 페이지
- `GET /api/stocks` - 분석 가능한 종목 목록
- `GET /api/models` - 사용 가능한 AI 모델 목록
- `POST /api/analyze` - 종목 분석 실행
- `GET /api/quick-info/{ticker}` - 종목 간단 정보

## 💡 사용 예시

### Python API 직접 호출
```python
from agent_test.stock_analyzer_agent import run_stock_analysis_agent

result = run_stock_analysis_agent(
    ticker="005930.KS",
    profile="balanced",
    model_name="gpt-4o-mini"
)

print(result['recommendation']['rating'])  # BUY/HOLD/SELL
```

### HTTP API 호출
```bash
curl -X POST http://localhost:8001/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "005930.KS",
    "profile": "balanced",
    "model_name": "gpt-4o-mini"
  }'
```

## 🔄 데이터 업데이트 주기

- **주가 데이터**: 매일 1회 (장 마감 후)
- **재무 데이터**: 분기별 (실적 발표 후)
- **기술적 지표**: 주가 업데이트 후 즉시
- **뉴스 데이터**: 실시간 (Qdrant 검색)

## 📚 참고

- 포트폴리오 분석: `experiments/portfolio_endpoint.py`
- LLM 클라이언트: `core/llm_clients.py`
- DB 유틸: `core/db.py`
- 벡터 DB: `core/vector_db.py`

---

**Made with ❤️ using FastAPI, Anthropic Claude, and PostgreSQL**
