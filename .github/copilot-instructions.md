# Copilot 개발 가이드: sector-portfolio-agent

> LangGraph + RAG 아키텍처를 활용한 AI 기반 섹터 포트폴리오 생성기

## 아키텍처 개요

이 프로젝트는 **LangGraph 상태 머신** 기반의 멀티 에이전트 투자 분석 시스템입니다:

### 핵심 컴포넌트

1. **FastAPI 서버** (`main.py`)
   - `/generate-portfolio-v1` 엔드포인트 제공
   - 생명주기 관리: 시작 시 모든 LangGraph 엔진 컴파일, 모델 가용성 검증
   - `.env` API 키 기반 동적 모델 선택

2. **LangGraph 엔진** (`core/graph_builder.py`)
   - **AgentState**: 타입 안전 상태 컨테이너 (sector_name, messages, iteration_count, momentum_result, realtime_news_result, historical_news_result, final_report)
   - **Coordinator 노드**: LLM 기반 도구 선택 의사결정
   - **Tool Executor 노드**: 3개 도구 실행, AgentState 구획에 결과 저장
   - **Report Generator 노드**: 최종 분석 보고서 생성
   - **Router**: 조건부 라우팅 (tool_calls 존재 여부, 최대 7회 반복 제한)
   - 도구는 순차 실행, 결과는 루프 반복 전체에서 유지됨

3. **다중 소스 데이터 수집** (`agents/tools.py`) - 3개 도구 병렬 실행
   - **`get_sector_etf_momentum(sector_name)`**: yfinance 3개월 데이터 → SMA_50 모멘텀
     - 반환: `{"ticker", "latest_close", "sma_50", "momentum_signal"}`
   
   - **`search_realtime_news_tavily(query)`**: Tavily Search API → 최신 뉴스
     - 반환: List[Dict] (최대 10개, 요약된 콘텐츠 포함)
   
   - **`search_sector_news_qdrant(sector_name)`**: ⭐ **Qdrant 순수 검색** (Firecrawl 제거)
     - 데이터: 기존 49,605개 뉴스 (multilingual-e5-large 1024차원 임베딩)
     - 프로세스:
       1. Query encoding ("query: " 접두사 추가)
       2. Qdrant 벡터 검색 (상위 100개, 유사도 >0.5)
       3. 종합 점수 계산: `similarity * 0.5 + sentiment_confidence * 0.3 + source_trust * 0.2`
       4. 상위 10개만 선정
       5. 감성 통계: positive/neutral/negative 비율 + 평균 신뢰도
     - 반환: `{"query", "total_results", "sentiment_stats", "news"}` 

4. **LLM 팩토리** (`core/llm_clients.py`)
   - 지원 모델: Upstage (solar-pro2), OpenAI (gpt-4o), Google Gemini, Groq
   - `.env` API 키 있는 엔진만 `compiled_engine_map`에 등록
   - 없는 키는 건너뜀 (우아한 폴백)
   - `AVAILABLE_MODELS`: 모든 설정 모델 | `compiled_engine_map`: 실제 작동 엔진만

5. **벡터 데이터베이스** (`core/vector_db.py`)
   - Qdrant 싱글톤 팩토리
   - 프로덕션: Qdrant Cloud (QDRANT_URL + QDRANT_API_KEY)
   - 개발: 로컬 `:memory:` 모드 (설정 불필요)

6. **감성분석** (`agents/sentiment_analyzer.py`)
   - **하이브리드 3단계 전략**:
     1. 사전 기반 (금융 키워드, 0.001초/텍스트)
     2. FinBERT-KR (GPU 인식, 캐싱, 고신뢰도 재분석)
     3. FinBERT 불가 시 사전 기반으로 폴백
   - 캐시: `./cache/finbert/sentiment_cache.json`

### 데이터 흐름

```
┌─ FastAPI Request ─────────────────────────────┐
│  /generate-portfolio-v1                       │
│  sector_name="반도체", model="solar-pro2"    │
└────────────────────┬──────────────────────────┘
                     │
                     ▼
    ┌─ main.py ──────────────────────┐
    │ • load_dotenv() 실행            │
    │ • 모델 가용성 검증              │
    │ • compiled_engine 선택          │
    └──────────────┬──────────────────┘
                   │
                   ▼
    ┌─ graph_builder.py ──────────────────────────┐
    │ Step 1: coordinator_node                    │
    │ ├─ 프롬프트: "3개 도구 모두 호출"         │
    │ ├─ tool_calls 생성:                        │
    │ │  ① get_sector_etf_momentum()            │
    │ │  ② search_realtime_news_tavily()       │
    │ │  ③ search_sector_news_qdrant()        │
    │ └─ LLM이 ToolMessage 반환                  │
    └──────────────┬────────────────────────────┘
                   │
                   ▼
    ┌─ tool_executor_node ──────────────────────────┐
    │ 3개 도구 병렬 실행:                           │
    │                                              │
    │ ① momentum_result:                          │
    │    {"ticker": "SOXX", "latest_close": 500, │
    │     "sma_50": 480, "momentum_signal": "Pos"}│
    │                                              │
    │ ② realtime_news_result:                    │
    │    [{"title": "...", "url": "..."}]        │
    │    (최대 10개 Tavily 결과)                   │
    │                                              │
    │ ③ historical_news_result:                  │
    │    {"query": "반도체", "total_results": 10,│
    │     "sentiment_stats": {                    │
    │       "positive": 6, "neutral": 3,         │
    │       "negative": 1,                        │
    │       "avg_sentiment_score": 0.45,        │
    │       "avg_confidence": 0.82               │
    │     },                                      │
    │     "news": [{...} ✕ 10]}                 │
    │                                              │
    │ AgentState 업데이트 후 반환                  │
    └──────────────┬────────────────────────────┘
                   │
                   ▼
    ┌─ router_node ──────────────────┐
    │ tool_calls 있었나? YES         │
    │ iteration_count >= 7? NO       │
    │ → report_generator로 이동    │
    └──────────────┬─────────────────┘
                   │
                   ▼
    ┌─ report_generator_node ────────────────┐
    │ 최종 보고서 생성:                      │
    │ • 모멘텀 분석 (yfinance)               │
    │ • 실시간 뉴스 (Tavily 10개)           │
    │ • 역사적 뉴스 (Qdrant 10개)           │
    │ • 감성 통계 (positive/negative)      │
    │                                       │
    │ → final_report 작성                   │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─ 응답 ────────────────────┐
    │ {"sector": "반도체",       │
    │  "model": "solar-pro2",  │
    │  "final_report": "..."}  │
    └────────────────────────────┘
```

## 중요 관례

### 환경 설정 및 API 키

**필수 요소**:
```bash
# LLM 모델 선택
LLM_PROVIDER_UPSTAGE_MODEL=solar-pro2
LLM_PROVIDER_OPENAI_MODEL=gpt-4o
UPSTAGE_API_KEY=xxxx
OPENAI_API_KEY=xxxx

# 도구 API (필수)
TAVILY_API_KEY=tvly_xxxx  # 실시간 뉴스 검색

# Qdrant (클라우드/선택)
QDRANT_URL=https://xxxx.qdrant.io
QDRANT_API_KEY=qdrant_xxxx
# (없으면 로컬 :memory: 모드 자동)

# PostgreSQL (배치 작업용, 선택)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=finlab
DB_USER=finuser
DB_PASS=xxxx
```

**로드 순서 (중요)**:
```python
# main.py
load_dotenv()  # ← 이 줄이 가장 먼저
from core.llm_clients import AVAILABLE_MODELS  # ← 그 다음
from core.graph_builder import compiled_engine_map  # ← 마지막
```

### 상태 관리 패턴

```python
# ✅ 올바름: AgentState에 업데이트 유지
def tool_executor_node(state: AgentState):
    momentum_result = state.get("momentum_result")
    # ... momentum_result 수정 ...
    return {
        "messages": tool_messages,
        "momentum_result": momentum_result,  # ← 명시적 반환
    }

# ❌ 잘못됨: 상태 딕셔너리 직접 수정
state["momentum_result"] = ...  # LangGraph가 유지하지 않음
```

### 도구 개발 패턴

```python
from langchain_core.tools import tool

@tool
def my_tool(param: str) -> dict:
    """도구 설명 (LLM과 Swagger에 표시됨)"""
    return {"key": "value"}  # 단순 dict/list만 반환

# agents/tools.py에서
available_tools = [
    get_sector_etf_momentum,
    search_realtime_news_tavily,
    search_sector_news_qdrant,
    my_tool,  # 새 도구 추가
]
```

### Qdrant 검색 결과 상세 포맷

```python
search_sector_news_qdrant("반도체") 반환값:
{
    "query": "반도체",
    "total_results": 10,  # 최종 선정된 개수
    "sentiment_stats": {
        "positive": 6,           # positive 뉴스 개수
        "neutral": 3,            # neutral 뉴스 개수
        "negative": 1,           # negative 뉴스 개수
        "avg_sentiment_score": 0.45,   # -1~1 범위
        "avg_confidence": 0.82   # 모델 신뢰도 평균
    },
    "news": [
        {
            "combined_score": 0.82,  # 최종 종합 점수
            "similarity_score": 0.85,  # Qdrant 유사도
            "title": "삼성전자 반도체 부문 실적 개선",
            "sentiment": "positive",  # 감성분석 결과
            "sentiment_score": 0.6,
            "sentiment_confidence": 0.92,
            "source": "hankyung.com",
            "published_at": "2025-11-11",
            "text_preview": "삼성전자의 반도체 부문이..."  # 150자
        },
        # ... 총 10개 ...
    ]
}
```

## 개발자 워크플로우

### 1. 서버 실행

```powershell
# 의존성 설치
uv sync --extra dev

# PostgreSQL 데이터 초기화 (선택, 배치 작업용)
python jobs/seed_companies.py

# FastAPI 시작
uvicorn main:app --reload
# → http://127.0.0.1:8000

# Swagger UI 확인
# → http://127.0.0.1:8000/docs
```

### 2. 엔드포인트 호출

```bash
# PowerShell
$url = "http://127.0.0.1:8000/generate-portfolio-v1?sector_name=반도체&model=solar-pro2"
$response = Invoke-RestMethod -Uri $url -Method Post
$response.final_report
```

### 3. 디버깅 및 모니터링

**모델 로딩 확인** - 서버 시작 로그:
```
--- [LLM Factory] Upstage 'solar-pro2' 모델을 로드합니다. ---
--- [LLM Factory] OpenAI 'gpt-4o' 모델을 로드합니다. ---
--- [Graph] LangGraph 엔진 맵 컴파일 완료 ---
--- [Graph] 총 2개의 엔진이 준비되었습니다: ['solar-pro2', 'gpt-4o'] ---
```

**Qdrant 데이터 상태** - Python REPL:
```python
from core.vector_db import qdrant_client
collection = qdrant_client.get_collection("sector_news_v2")
print(f"포인트 개수: {collection.points_count:,}")  # 49,605개
print(f"벡터 차원: {collection.config.params.vectors.size}")  # 1024
```

**LangGraph 실행 추적** - 로그에서:
```
--- [Graph] Node: Coordinator (Step 1/7) ---
[Agent 2 Tool] '반도체' 모멘텀 분석 시작...
[Agent 5 Tool - Tavily] 실시간 검색 완료. 10개 결과 반환.
[Agent 5 Tool - Qdrant] 섹터 뉴스 검색 시작: '반도체'
--- [Graph] Node: Report Generator (Step 1) ---
```

### 4. 새 도구 추가 (5단계)

**Step 1: 도구 정의** (`agents/tools.py`)
```python
@tool
def get_company_news_volume(ticker: str) -> dict:
    """특정 기업의 최근 뉴스 언급 빈도"""
    return {"ticker": ticker, "news_volume": 150, "trend": "up"}
```

**Step 2: 도구 리스트에 추가**
```python
available_tools = [
    get_sector_etf_momentum,
    search_realtime_news_tavily,
    search_sector_news_qdrant,
    get_company_news_volume,  # 새 도구
]
```

**Step 3: AgentState 확장** (`core/graph_builder.py`)
```python
class AgentState(TypedDict):
    # ... 기존 필드 ...
    company_volume_result: dict  # 새 필드 추가
```

**Step 4: tool_executor_node 업데이트**
```python
def tool_executor_node(state: AgentState):
    # ... 기존 코드 ...
    company_volume_result = state.get("company_volume_result", {})
    
    for call in tool_calls:
        if call["name"] == "get_company_news_volume":
            company_volume_result = t.invoke(call["args"])
    
    return {
        "messages": tool_messages,
        "company_volume_result": company_volume_result,  # 반환
    }
```

**Step 5: Coordinator 프롬프트 업데이트**
```python
initial_prompt = f"""
아래 4개의 도구를 *모두* 호출하세요:
1. get_sector_etf_momentum(sector_name="{state['sector_name']}")
2. search_realtime_news_tavily(query="{tavily_query}")
3. search_sector_news_qdrant(sector_name="{qdrant_query}")
4. get_company_news_volume(ticker="005930")  # 새 도구
"""
```

## 흔한 문제점 및 해결책

| 문제 | 원인 | 해결책 |
|------|------|--------|
| 모델 로딩 실패 | `.env` 파일 없음 또는 API 키 누락 | 루트에 `.env` 파일 생성, API 키 추가 |
| "모델은 사용 가능하지 않습니다" | API 키 없는 모델 선택 | Swagger 드롭다운에서 표시된 모델만 선택 |
| Qdrant 연결 오류 | QDRANT_URL/API_KEY 누락 | 클라우드 설정 또는 로컬 :memory: 모드 사용 |
| Tavily 검색 실패 | TAVILY_API_KEY 없음 | Tavily에서 API 키 발급 후 .env에 등록 |
| 도구 결과 "손실" | 노드에서 모든 필드 반환 안 함 | `tool_executor_node`에서 상태 필드 명시적 반환 |
| ToolMessage 에러 | `tool_call_id` 미매칭 | `call["id"]`를 정확히 ToolMessage에 전달 |
| Qdrant 검색 결과 0개 | 컬렉션 데이터 부족 | `_check_qdrant_collection()` 로그 확인, 데이터 재수집 |

## 핵심 코드 패턴

### LangGraph 상태 업데이트 패턴 (필수)

```python
# ✅ 올바름: 반환 딕셔너리로 상태 업데이트
def tool_executor_node(state: AgentState):
    momentum_result = state.get("momentum_result", {})
    # ... 도구 실행 및 수정 ...
    return {
        "messages": tool_messages,
        "momentum_result": momentum_result,  # 명시적 반환
    }

# ❌ 잘못됨: 직접 수정은 LangGraph에서 감지 안 함
state["momentum_result"] = result  # 이 방식은 작동 안 함!
```

### Tavily 결과 처리

```python
from langchain_community.tools.tavily_search import TavilySearchResults

tavily = TavilySearchResults(max_results=10, tavily_api_key=TAVILY_API_KEY)
results = tavily.invoke("반도체 sector latest news")
# 결과: [{"title": "...", "url": "...", "content": "..."}]
```

### Qdrant 벡터 검색 패턴

```python
from sentence_transformers import SentenceTransformer

embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')

# E5 모델은 "query: " 접두사가 필수 (검색 품질 향상)
query_vector = embedding_model.encode("query: 반도체 섹터 분석").tolist()

results = qdrant_client.search(
    collection_name="sector_news_v2",
    query_vector=query_vector,
    limit=100,  # 상위 100개 먼저 검색
    score_threshold=0.5  # 유사도 50% 이상만
)
```

## 핵심 파일 참고

| 파일 | 용도 | 주요 함수 |
|------|---------|---|
| `main.py` | FastAPI 진입점 | `generate_portfolio_v1()`, 생명주기 관리자 |
| `core/graph_builder.py` | LangGraph 조율 | `create_graph_engine()`, `compiled_engine_map` |
| `core/llm_clients.py` | LLM 팩토리 | `get_chat_model()`, `AVAILABLE_MODELS` |
| `agents/tools.py` | 도구 정의 | `get_sector_etf_momentum`, `search_realtime_news_tavily`, `ingest_and_search_qdrant` |
| `core/vector_db.py` | Qdrant 싱글톤 | `qdrant_client` |
| `agents/sentiment_analyzer.py` | 하이브리드 감성분석 | `HybridSentimentAnalyzer`, `FinBERTAnalyzer` |
| `core/db.py` | PostgreSQL 헬퍼 | `exec_sql()`, `fetch_dicts()` |

---

**버전**: 1.0 | **Python**: ≥3.10 | **프레임워크**: LangGraph + FastAPI
