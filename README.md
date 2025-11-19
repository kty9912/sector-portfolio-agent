# Sector Portfolio Agent

AI 기반 섹터 포트폴리오 분석기 — LangGraph / Anthropic / OpenAI 등 LLM 엔진을 활용하여 섹터·종목 분석과 포트폴리오 구성을 자동 생성하는 연구용/프로토타입 서비스입니다.

---

목차
- 프로젝트 개요
- 빠른 시작(Windows / PowerShell)
- 요구사항(환경, 의존성)
- 환경 변수(.env)
- 실행(로컬, Docker)
- API 레퍼런스 (핵심 엔드포인트)
- 프론트엔드 사용법(포트폴리오 화면 요약)
- PDF 다운로드(생성) 흐름과 모바일 문제 해결 가이드
- 개발자 가이드 (코드 구조, 테스트, 린트)
- 배포/운영 팁 (Playwright, 브라우저, 인증)
- 문제 해결(FAQ)
- 기여, 라이선스, 연락처

---

## 프로젝트 개요

이 저장소는 LLM(Anthropic, LangGraph, OpenAI 등)과 다양한 도구(yfinance, qdrant 등)를 결합해 다음을 수행합니다:

- 섹터/종목 후보 선정 및 스코어링
- 재무·시세·뉴스 데이터 수집 및 분석
- 포트폴리오 구성(비중 산정) 및 예상 수익/리스크 지표 생성
- 차트(Plotly)와 보고서(PDF) 생성

디렉터리 요약(주요 디렉터리/파일)

- `agents/` — AI 에이전트 구현 (portfolio_agent_anthropic.py, portfolio_agent_multi.py 등)
- `core/` — 데이터베이스, 벡터 DB, LLM 클라이언트 래퍼 등 (db.py, vector_db.py, llm_clients.py)
- `jobs/` — 배치성 데이터 로드/처리 스크립트 (load_prices_daily.py 등)
- `templates/` — 정적 파일(HTML/CSS/JS) 프론트엔드 템플릿
- `main.py` — FastAPI 서버 진입점 및 HTTP API 엔드포인트
- `pyproject.toml` — 프로젝트 메타/의존성

## 빠른 시작 (Windows PowerShell)

아래 명령은 Windows PowerShell 기준입니다. 다른 운영체제에서는 가상환경 활성화/명령어가 다를 수 있습니다.

1) 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) pip 최신화 및 설치

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -e .
# 또는 필요에 따라: pip install -r requirements.txt
```

3) 환경 변수 설정

프로젝트 루트에 `.env` 파일(또는 환경변수)을 만들어 아래 예시를 채우세요. `.env.example` 파일을 함께 제공합니다.

4) 개발 서버 실행 (FastAPI)

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

웹브라우저에서 `http://localhost:8000/` 또는 `http://localhost:8000/portfolio`를 열어 UI를 확인하세요.

---

## 요구사항

- Python 3.10 이상 (pyproject.toml의 requires-python 참조)
- 주요 라이브러리: FastAPI, uvicorn, python-dotenv, openai, anthropic, yfinance, pandas, langchain, plotly, playwright, sentence-transformers, qdrant-client 등(자세한 항목은 `pyproject.toml` 참조)
- Playwright 사용 시 시스템에 브라우저가 필요합니다. 로컬: `playwright install` 또는 `playwright install chromium` 실행

권장: 충분한 메모리(특히 transformers/torch 사용 시)와 네트워크 접근(LLM API, 외부 데이터 소스)

---

## 실행(로컬 & Docker)

로컬(권장 개발)

1) 가상환경 활성화 및 설치(위 섹션 참조)
2) `uvicorn main:app --reload`로 개발 서버 실행

Docker (기본)

1) 이미지 빌드

```powershell
docker build -t sector-portfolio-agent .
```

2) 컨테이너 실행 (예: 포트 8000 노출)

```powershell
docker run --rm -it -p 8000:8000 \
  -e OPENAI_API_KEY="your_key" \
  -e ANTHROPIC_API_KEY="your_key" \
  sector-portfolio-agent
```

Playwright 관련: Docker 이미지에 Playwright 브라우저가 포함되어 있지 않으면 `playwright install --with-deps` 또는 도커파일에 필요한 패키지를 추가해야 합니다. 브라우저 포함 이미지 또는 chrome/chromium이 설치된 베이스 이미지를 사용하세요.

---

## API 레퍼런스(핵심)

아래는 `main.py`에 정의된 핵심 엔드포인트(요약)입니다. 인증/권한이 있는 경우 환경에 맞춰 추가하세요.

기본 페이지
- GET `/` → `templates/index.html`
- GET `/portfolio` → `templates/portfolio.html`
- GET `/stock` → `templates/stock.html`

데이터 조회
- GET `/api/sectors` → 사용 가능한 섹터 리스트 (JSON)
- GET `/api/stocks` → 사용 가능한 종목 리스트 (JSON)
- GET `/api/models` → 사용 가능한 LLM 모델 목록 (JSON)

분석 요청
- POST `/api/analyze/anthropic` → Anthropic 기반 포트폴리오 분석
- POST `/api/analyze/langgraph` → LangGraph 기반 포트폴리오 분석

종목 관련
- POST `/api/stock/anthropic` → 종목 단위 Anthropic 분석 (JSON body: ticker, profile, model_name)
- POST `/api/stock/langgraph` → 종목 단위 LangGraph 분석

PDF 생성/다운로드
- POST `/api/stock/download-pdf` → 서버사이드(Playwright)로 HTML을 렌더하여 PDF 생성 후 StreamingResponse로 반환(attachment header 포함)
- POST `/api/download-pdf` → (비슷한 기능; 코드 내 다른 엔드포인트가 존재할 수 있음)

유틸
- GET `/api/quick-info/{ticker}` → 종목 간단 정보 (DB 또는 yfinance fallback)
- GET `/api/chart-data/{ticker}` → 차트용 시세/재무 데이터
- GET `/api/sector-comparison/{ticker}` → 섹터 내 비교 데이터

예시: PowerShell(curl)로 Anthropic 분석 호출

```powershell
$body = @{
  budget = 1000000
  investment_targets = @{ sectors = @('IT') ; tickers = @('005930.KS') }
  risk_profile = '중립'
  investment_period = '중기'
  model_name = 'solar-pro2'
  additional_prompt = ''
} | ConvertTo-Json -Depth 5

curl -X POST "http://localhost:8000/api/analyze/anthropic" -H "Content-Type: application/json" -d $body
```

PDF 생성 예시(프론트엔드에서 HTML 전송)

```javascript
// fetch 방식(현재 프로젝트의 portfolio.js에서 사용될 가능성 있음)
fetch('/api/stock/download-pdf', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ html: htmlContent })
})
.then(res => res.blob())
.then(blob => {
  // 데스크톱에서 동작할 수 있으나 모바일/특정 WebView에선 실패 가능
});
```

더 안정적인 방법(모바일 호환성 개선): 서버로 HTML을 POST할 때 숨겨진 `<form>`으로 `target="_blank"` 제출

```javascript
const form = document.createElement('form');
form.method = 'POST';
form.action = '/api/stock/download-pdf';
form.target = '_blank';
form.style.display = 'none';

const input = document.createElement('input');
input.name = 'html';
input.value = htmlContent; // 긴 문자열일 경우 서버사이드에서 처리 허용
form.appendChild(input);
document.body.appendChild(form);
form.submit();
form.remove();
```

이 방식은 브라우저 네비게이션을 사용하므로 모바일(iOS/Android)에서 기본 다운로드 동작을 유도하기 더 쉽습니다.

---

## 프론트엔드(포트폴리오 페이지) 사용법 요약

템플릿: `templates/portfolio.html` + `templates/portfolio.js`

주요 동작
- 섹터/종목 선택 → 예산/성향 입력 → 분석 버튼 클릭
- 분석 요청은 `/api/analyze/*`로 POST, 결과가 오면 차트 및 표 렌더링
- 결과 화면에서 'PDF 다운로드' 버튼을 누르면 HTML(현재 결과)를 서버로 전송해 Playwright로 PDF를 생성합니다.

주의: `portfolio.js`의 현재 구현은 `fetch` 기반으로 PDF 바이트를 받아 client-side에서 다운로드를 시도하는 블록이 생략되어 있습니다. 모바일 환경(iOS Safari, 일부 WebView)은 blob→download 동작을 지원하지 않을 수 있으므로 위에 제시한 `form` 방식이나 presigned URL 방식으로 대체하는 것을 권장합니다.

---

## PDF 생성 흐름 및 모바일 문제(상세)

서버 측
- 엔드포인트는 Playwright를 사용해 HTML을 렌더링하고 `page.pdf()`로 PDF 바이트를 생성합니다.
- 서버는 `StreamingResponse`로 PDF 바이트를 전달하며, 헤더에 `Content-Disposition: attachment; filename=...`을 설정합니다(다운로드를 강제).

문제(모바일에서 종종 발생)

1) 프론트엔드가 `fetch`로 PDF를 받아 `blob`을 만들고 `a.download`로 다운로드를 트리거하면 iOS Safari나 일부 WebView에서 이 동작이 제한되어 저장이 불가함.
2) fetch 시 CORS/credentials 설정 오류로 실제로 PDF가 아닌 HTML(로그인 페이지 등)이 내려와 실패할 수 있음.
3) 인앱(WebView)에서는 브라우저의 다운로드 매니저가 없어 저장이 안될 수 있음.

권장 해결(우선순위)

1. 가장 간단한 방법: 프론트엔드에서 fetch 대신 `form` submit(target=_blank)으로 POST하여 브라우저가 직접 서버 응답을 수신하게 함 — 모바일 친화적.
2. 또는 서버에서 PDF를 먼저 생성하고 파일 URL(presigned URL 또는 정적 경로)을 반환 → 프론트엔드에서 `window.open(url)` 또는 `<a href>`로 열기.
3. 인앱(WebView) 사용자에게는 외부 브라우저에서 열도록 유도하거나 앱 네이티브 쪽에서 다운로드 처리 로직을 추가.

테스트 체크리스트

- PowerShell로 모바일 User-Agent 흉내내어 헤더 확인:

```powershell
$ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
curl -I -A $ua "http://localhost:8000/api/stock/download-pdf"
```

- 모바일에서 버튼 클릭 시 개발자 도구 또는 프록시(Charles, Fiddler)로 요청/응답 확인(응답 Content-Type, Content-Disposition, 실제 바이트 여부)

---

## 개발자 가이드

코드 구조(재요약)

- `main.py` — FastAPI 라우트 및 PDF 생성 엔드포인트
- `agents/` — 각종 에이전트 로직
- `core/` — DB, vector DB, LLM 클라이언트
- `templates/` — 프론트엔드 자산

테스트/린트

- 테스트: `pytest` (dev 의존성)
- 린트: `ruff` 또는 `flake8` (pyproject에 dev 의존성으로 명시되어 있음)

로컬 디버깅 팁

- Playwright 에러 시: `playwright install`을 실행하고 필요시 `playwright install-deps` (Linux) 또는 브라우저 설치를 확인하세요.
- yfinance 관련 SSL 오류가 날 경우 `CERT_PATH`를 `C:\certs\cacert.pem` 같은 경로로 지정했는지 확인하거나 OS의 CA를 갱신하세요. `main.py`에 관련 체크가 있으므로 해당 파일에 맞게 경로를 설정하면 됩니다.

코드 변경 제안(간단)

- PDF 다운로드: `portfolio.js`의 다운로드 핸들러를 blob 방식에서 form-submit/presigned-url 방식으로 변경(모바일 호환성 향상).
- 인증이 필요한 환경이면 presigned URL 또는 토큰 기반 GET으로 변경.

---

## 배포/운영 팁

- Playwright를 프로덕션 컨테이너에 넣을 때는 브라우저(Chromium) 및 필요한 OS 패키지를 도커파일에 포함해야 합니다.
- LLM API 키는 반드시 안전하게 보관(Secrets Manager, GitHub Actions Secrets 등)하고 로컬에만 `.env`로 보관하세요.
- 대용량 요청/동시성: PDF 생성은 리소스(브라우저 프로세스 + 메모리)를 소모하므로 워커/큐(RQ, Celery 등)로 비동기 처리하는 것을 권장합니다.

---

## 문제 해결(FAQ)

Q: 모바일에서 PDF가 다운로드되지 않아요.
A: 프론트엔드가 fetch→blob→a.download 패턴을 쓰면 iOS/WebView에서 동작하지 않습니다. 가장 빠른 해결은 `form`으로 `target=_blank` 제출하거나 서버에서 presigned URL을 만들어 제공하는 것입니다. (상세 내용은 위 섹션 참조)

Q: Playwright에서 차트(Plotly)가 렌더링되지 않아요.
A: PDF 렌더링 전에 `page.wait_for_load_state('networkidle')`와 추가 `page.wait_for_timeout(2000~5000)`을 넣어 차트 스크립트/데이터 바인딩이 완료되도록 하세요. CSS/폰트 외부 로드도 완료되었는지 확인합니다.

Q: yfinance가 SSL 인증 에러를 냅니다.
A: `CERT_PATH`를 `C:\certs\cacert.pem` 같은 경로로 지정했는지 확인하거나 OS의 CA를 갱신하세요. `main.py`에 관련 체크가 있으므로 해당 파일에 맞게 경로를 설정하면 됩니다.

---

## 기여 / 라이선스 / 연락처

- 기여: 이슈 열기 → PR 생성 → 리뷰(테스트 포함 권장)
- 라이선스: 별도 명시가 없으면 내부 논의 후 명시하세요(예: MIT)
- 연락처: 저장소 소유자(또는 maintainer) GitHub 프로필 또는 이메일

---

### 변경 기록

- README 초안 작성 — 매우 상세한 설치/운영/디버깅 지침 포함

---

끝.
# sector-portfolio-agent
Investment AI Agent Building
