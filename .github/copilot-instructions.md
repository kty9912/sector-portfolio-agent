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

3. **다중 소스 데이터 수집** (`agents/tools.py`)
   - `get_sector_etf_momentum`: yfinance → SMA_50 모멘텀 신호
   - `search_realtime_news_tavily`: Tavily API → 실시간 뉴스 요약
   - `search_sector_news_qdrant`: Qdrant RAG 

4. **LLM 팩토리** (`core/llm_clients.py`)
   - 지원 모델: Upstage (solar-pro2), OpenAI (gpt-4o-mini), Google Gemini, Groq
   - `.env` API 키 있는 엔진만 컴파일; 키 없음 = 건너뜀
   - AVAILABLE_MODELS = 모든 설정 모델 (Swagger enum용); compiled_engine_map = 작동하는 모델만

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
FastAPI 요청
  → main.py: 모델 가용성 검증
  → graph_builder.py:coordinator_node (프롬프트: "3개 도구로 섹터 분석")
  → 조건부 라우팅: router_node (tool_calls 있는가?)
  → [예] tool_executor_node (3개 도구 모두 실행)
    → momentum_result, realtime_news_result, historical_news_result가 AgentState에서 업데이트됨
  → router_node (7회 도달? 모든 도구 완료?)
  → [예] report_generator_node (최종 보고서 생성)
  → [아니오] coordinator_node (다음 반복, 업데이트된 상태 참조)
  → final_report와 함께 응답
```

## 중요 관례

### 환경 설정

- **로드 순서가 중요**: `main.py`가 `core/*` 모듈 임포트 **이전에** `load_dotenv()` 호출해야 함
- **API 키 의존성**:
  ```
  LLM_PROVIDER_UPSTAGE_MODEL=solar-pro2 (기본값)
  LLM_PROVIDER_OPENAI_MODEL=gpt-4o (기본값)
  TAVILY_API_KEY (실시간 뉴스 필수)
  FIRECRAWL_API_KEY (심층 뉴스 크롤링 필수)
  QDRANT_URL + QDRANT_API_KEY (선택사항; 없으면 :memory:)
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

### 도구 결과 포맷

- 도구는 **단순 dict/list** 반환 (ToolMessage 아님)
- Tool executor가 `tool_call_id`로 ToolMessage에 래핑
- 도구는 `agents/tools.py`의 `@tool()` 데코레이터 함수

### Qdrant 컬렉션 스키마

컬렉션: `sector_news_v2` (1024차원 multilingual-e5-large 임베딩)
Payload 키:
- `text`, `title`, `sector`
- `sentiment`, `sentiment_score`, `sentiment_confidence`, `analysis_method`
- `source_url`, `source_domain`, `source_trust_score`
- `published_at`, `crawled_at`, `content_hash`
- `companies`, `tags` (TODO: NER 추출)

## 개발자 워크플로우

### 서버 실행

```powershell
# 의존성 설치
uv sync --extra dev

# FastAPI 시작 (localhost:8000)
uvicorn main:app --reload

# 엔드포인트 테스트
curl "http://127.0.0.1:8000/generate-portfolio-v1?sector_name=반도체&model=solar-pro2"
```

### 테스트 및 디버깅

1. **모델 로딩 확인**:
   ```python
   # 시작 시 서버 로그 모니터링:
   # "✅ LangGraph 엔진 컴파일 성공" → 모델 사용 가능
   # "⚠️ 건너뛰기" → API 키 없음
   ```

2. **Qdrant 데이터 검사**:
   ```python
   from core.vector_db import qdrant_client
   qdrant_client.get_collection("sector_news_v2")
   ```

3. **감성분석 디버깅**:
   - 사전 기반 결과는 즉시; FinBERT는 `./cache/finbert/`에 캐시됨
   - GPU 강제: torch CUDA 사용 가능 확인
   - CPU 모드: 자동 폴백, 4개 스레드 사용

4. **LangGraph 실행 추적**:
   - 로그 메시지 포함: `[Graph] Node: {name} (Step {iteration}/{recursion_limit})`
   - 조건부 라우터가 엣지 선택 이유 로깅

### 새 도구 추가

1. `agents/tools.py`에서 `@tool` 데코레이터로 정의
2. `available_tools` 리스트에 추가
3. `coordinator_node` 프롬프트 업데이트하여 도구 언급
4. `tool_executor_node` 업데이트하여 tool_name 처리 및 결과를 AgentState에 저장
5. 상태 딕셔너리에 저장된 결과: `tool_executor_node` 반환의 일부로 반환

## 흔한 문제점

| 문제 | 해결책 |
|-------|----------|
| 모델 로딩 안 됨 | `.env` 파일이 루트에 존재 확인; API 키 검증 |
| ToolMessage 에러 | `tool_call_id`가 LLM의 tool_calls와 일치 확인 |
| Qdrant 연결 안 됨 | 로컬 :memory: 모드 자동 활성화; 클라우드는 env 변수 필요 |
| FinBERT 느림/메모리 초과 | GPU 사용 가능? sentiment_analyzer.py의 `torch.cuda.is_available()` 확인 |
| 도구 실행 후 상태 "손실" | 노드 함수에서 모든 수정 필드 반환 |
| 7회 반복 이상 무한 루프 | Router가 `iteration_count >= 7`에서 `report_generator`로 강제 이동 |

## 예시: 새 도구 추가

```python
# agents/tools.py
@tool
def get_company_financials(ticker: str) -> dict:
    """4분기 실적 조회."""
    return {"eps": 1.5, "revenue_growth": 0.12}

# 리스트에 추가
available_tools.append(get_company_financials)

# graph_builder.py의 라우터 업데이트
def tool_executor_node(state: AgentState):
    # ... 기존 코드 ...
    if tool_name == "get_company_financials":
        financials_result = result  # 새 필드
    # ...
    return {
        "messages": tool_messages,
        "financials_result": financials_result,  # 새 상태 필드 반환
    }

# AgentState TypedDict 업데이트
class AgentState(TypedDict):
    # ... 기존 필드 ...
    financials_result: dict  # 새 필드
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
