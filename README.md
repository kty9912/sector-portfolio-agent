# 📈 금융 투자 전략 AI Agent  
AI 기반 멀티 에이전트 시스템으로 **포트폴리오 구성**, **기업 분석**, **투자 전략 생성**을 자동화하는 프로젝트입니다.

본 시스템은 재무·기술·뉴스 데이터를 통합 분석하여, 단순 지표 제공을 넘어서 **신뢰도 높은 투자 전략**을 산출하도록 설계되었습니다.

---

## 🚀 프로젝트 개요

**금융 투자 전략 AI Agent**는  
실시간 시장 데이터(시세, 재무, 뉴스)를 다각도로 분석하여  
사용자에게 **정교한 포트폴리오 추천**과 **기업 분석 기반 투자 전략**을 제공하는 멀티 에이전트 기반 서비스입니다.

- 멀티 에이전트 구조 (재무·기술·뉴스·통합 분석 전문가)
- LangGraph / Anthropic 방식 모두 지원
- HTML/CSS/JS 사용자 인터페이스
- Postgres + Qdrant 기반 데이터 저장 및 검색
- CI/CD 자동화 및 Docker 기반 배포

---

## 🧠 핵심 기능

### 1) ⭐ **포트폴리오 구성 서비스**
사용자 입력:
- 엔진 선택 (Anthropic / LangGraph)
- LLM 모델 선택 (OpenAI / Solar Pro 2 / Groq)
- 투자 예산
- 선호 섹터 / 종목
- 투자 성향
- 투자 기간

출력 기능:
- 최적 포트폴리오 구성 비율
- 각 종목에 대한 3대 전문가 의견(재무/뉴스/데이터 분석)
- AI 기반 종합 평가
- Sunburst 차트 & 예상 수익률 그래프
- PDF 다운로드

---

### 2) ⭐ **기업 분석 서비스**
입력:
- 엔진 선택
- LLM 모델 선택
- 종목(기업)
- 투자 성향
- 투자 기간

출력:
- 종합 점수 (재무/기술/뉴스 종합)
- 시장 현황 및 수익률 추세
- 기술적 지표 (RSI, MA, 모멘텀, 변동성 등)
- 재무 분석 (성장성·수익성·건전성)
- 벨류에이션 비교
- 시나리오 분석 (강세/중립/약세)
- 뉴스 감성 분석
- 투자 포인트 및 리스크 요약
- 매수/매도 힌트, 지지/저항 구간
- PDF 다운로드

(예시는 `/templates/stock.html` 및 산출된 PDF 참조)

---

## 🏗️ 시스템 아키텍처 개요

### 주요 구성 요소
- **FastAPI** 기반 백엔드 API
- **템플릿 기반 HTML/CSS/JS 프론트엔드**
- **Postgres**: 가격·재무·시그널 저장
- **Qdrant**: 뉴스 벡터 저장 및 검색
- **OpenAI, Solar Pro 2, Groq** LLM 지원
- **LangGraph 기반 Multi-Agent Workflow**
- **Docker 기반 컨테이너 운영**
- **Oracle Cloud(OCI)** 배포
- **Woodpecker CI/CD** 자동화

---

## 📂 폴더 구조
```
financial-strategy-agent
├── agents
│ ├── portfolio_agent_anthropic.py
│ ├── portfolio_agent_multi.py
│ ├── sentiment_analyzer.py
│ ├── stock_agent_anthropic.py
│ ├── stock_agent_langgraph.py
│ └── tools.py
│
├── core
│ ├── db.py
│ ├── graph_builder.py
│ ├── llm_clients.py
│ └── vector_db.py
│
├── experiments
│ └── test_llm_factory.py
│
├── jobs
│ ├── calc_signals_latest.py
│ ├── load_fundamentals.py
│ ├── load_prices_daily.py
│ ├── model_download.py
│ └── seed_companies.py
│
├── templates
│ ├── index.html / index.css
│ ├── portfolio.html / portfolio.css / portfolio.js
│ ├── stock.html / stock.css / stock.js
│
├── main.py
├── Dockerfile
├── .dockerignore
├── .gitignore
├── pyproject.toml
├── uv.lock
├── .woodpecker.yml
└── .venv
```

---

## ⚙️ 실행 방법

### ▶ 로컬 실행

`uv run python -m main`

또는

`python -m main`

---

## 🔑 환경 변수
```
다음 환경 변수가 필요합니다:

DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASS

OPENAI_API_KEY
UPSTAGE_API_KEY
TAVILY_API_KEY

LLM_PROVIDER
LLM_PROVIDER_OPENAI_MODEL

QDRANT_API_KEY
QDRANT_URL

GOOGLE_API_KEY
GROQ_API_KEY
```

`.env` 파일 또는 OS 환경 변수로 설정할 수 있습니다.

---

## 🐳 Docker / 배포 구조

- 배포 환경: **Oracle Cloud(OCI)**
- 백엔드 서비스와 Postgres는 **개별 Docker 이미지**로 실행
- Woodpecker CI는 **Docker Compose** 기반 자동화된 빌드/배포 구성
- Reverse Proxy 없이 FastAPI 서버 직접 운용

---

## 🧪 테스트

테스트 코드는 `experiments/` 디렉토리 내에 위치하며, 다음 항목들을 중심으로 작성 중입니다.

- LLM 클라이언트 초기화 테스트  
- Multi-Agent Workflow 정상 동작 테스트  
- 기술 지표 계산 및 데이터 정상성 테스트  
- JSON 파싱 및 리포트 생성 테스트  

(향후 pytest 기반 자동화 테스트 확장 예정)

---

## ⚠ 투자 유의사항

본 분석 결과는 **AI 알고리즘 기반의 참고 자료**이며,  
투자 권유나 종목 추천이 아닙니다.  

과거 데이터와 통계를 기반으로 생성되므로  
**미래 수익을 보장하지 않습니다.**  

모든 투자 결정과 그에 따른 손익은  
**투자자 본인의 책임**입니다.

---

## 📞 문의 / 개발자 정보

- 개발: 용신 ( 김태용, 신도희 )
- 목적: 교육/연구/프로토타입 개발용
- 문의: 프로젝트 이슈 탭 또는 개인 연락망

---
