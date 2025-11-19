# Sector Portfolio Agent

AI 기반 섹터 포트폴리오 분석기 — LangGraph / Anthropic / OpenAI 등 LLM 엔진을 활용하여 섹터·종목 분석과 포트폴리오 구성을 자동 생성하는 연구용/프로덕션 지향 서비스입니다.

Oracle Cloud(OCI) + Docker + PostgreSQL + Cloudflare Tunnel 기반으로 실제 서비스 환경에서 동작하도록 설계되어 있습니다.

---

## 📌 목차

- [프로젝트 개요](#-프로젝트-개요)
- [시스템 아키텍처 (프로덕션 기준)](#-시스템-아키텍처-프로덕션-기준)
- [로컬 개발 환경 (Windows 기준)](#-로컬-개발-환경-windows-기준)
- [요구사항](#-요구사항)
- [환경 변수 (.env)](#-환경-변수-env)
- [Docker 빌드 & 이미지 최적화](#-docker-빌드--이미지-최적화)
- [Oracle Cloud(OCI) 배포 가이드](#-oracle-cloudoci-배포-가이드)
- [Cloudflare Tunnel (무료 HTTPS)](#-cloudflare-tunnel-무료-https)
- [배치 작업 / Cron Jobs](#-배치-작업--cron-jobs)
- [핵심 API 레퍼런스](#-핵심-api-레퍼런스)
- [프론트엔드 & PDF 생성(Playwright)](#-프론트엔드--pdf-생성playwright)
- [문제 해결(FAQ)](#-문제-해결faq)
- [기여 / 라이선스 / 연락처](#-기여--라이선스--연락처)
- [변경 기록](#-변경-기록)

---

## 1️⃣ 프로젝트 개요

**Sector Portfolio Agent**는 다음 기능을 제공하는 AI 기반 포트폴리오 분석 시스템입니다.

- 섹터/종목 후보 선정 및 스코어링  
- 재무·시세·뉴스 데이터 수집 및 분석  
- 포트폴리오 구성(비중 산정) 및 예상 수익/리스크 지표 생성  
- 차트(Plotly) 및 PDF 기반 리포트 생성 (Playwright 사용)  
- LLM 기반 멀티 에이전트 구조 (LangGraph / Anthropic / OpenAI)

### 주요 디렉터리 구조

```text
agents/        # AI 에이전트 로직
core/          # DB, LLM Client, Vector DB 등 핵심 모듈
jobs/          # 일일/주기 배치 작업 스크립트
templates/     # HTML/CSS/JS 프론트엔드 템플릿
main.py        # FastAPI 엔트리 포인트
pyproject.toml # Python 프로젝트 메타/의존성
uv.lock        # uv 의존성 잠금 파일
```

---

## 2️⃣ 시스템 아키텍처 (프로덕션 기준)

### OCI + Docker + Cloudflare Tunnel 구조

```text
┌────────────────────────────────────────────────────────┐
│                   Oracle Cloud Free Tier               │
│   (Ampere ARM VM + Docker Runtime + PostgreSQL)        │
│                                                        │
│  ┌───────────┐        ┌──────────────┐                 │
│  │ FastAPI   │<------>│ PostgreSQL   │                 │
│  │ (Docker)  │        │ (Docker)     │                 │
│  └───────────┘        └──────────────┘                 │
│                                                        │
│      jobs/*.py → 일일 가격/지표/재무 업데이트          │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Cloudflare Tunnel (HTTPS)                       │  │
│  │ https://xxxx.trycloudflare.com → localhost:8000 │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

특징:

- **100% 무료 인프라** (OCI Free Tier + Cloudflare Tunnel)
- HTTPS 적용 (자체 SSL 인증서 불필요)
- Docker 이미지 최적화: **2.7GB → 442MB**
- Docker `--restart unless-stopped`로 컨테이너 장애 시 자동 재기동
- 서버 재부팅 시 `cloudflared`만 재실행하면 외부 접근 복구 가능

---

## 3️⃣ 로컬 개발 환경 (Windows 기준)

> 다른 OS에서도 동작하지만, venv 활성화/경로는 OS별로 차이가 있을 수 있습니다.

### 1) 가상환경 생성 & 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) 의존성 설치

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -e .
# 또는 uv 사용 시: uv sync
```

### 3) 개발 서버 실행

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서:

- http://localhost:8000/
- http://localhost:8000/portfolio
- http://localhost:8000/stock

등을 열어 UI를 확인합니다.

---

## 4️⃣ 요구사항

- Python 3.10 이상 (정확 버전은 `pyproject.toml` 참고)
- 주요 라이브러리:
  - `fastapi`, `uvicorn`, `python-dotenv`
  - `openai`, `anthropic`, `langchain`, `langgraph`
  - `pandas`, `numpy`, `plotly`
  - `qdrant-client`, `sentence-transformers`
  - `psycopg2` 또는 `psycopg[binary]` 등
  - `playwright` (PDF 생성 시)
- Playwright 사용 시:
  - 로컬: `playwright install` 또는 `playwright install chromium` 필요
  - Linux/Docker: 브라우저 & 필요한 시스템 패키지 설치 필요

권장 환경:

- 충분한 메모리 (torch/transformers 사용 시 중요)
- LLM API 및 외부 데이터(yfinance, 뉴스 등)에 접근 가능한 네트워크

---

## 5️⃣ 환경 변수 (.env)

프로젝트 루트에 `.env` 파일을 생성하고 아래 예시를 참고하여 값을 채웁니다.

```env
# LLM / API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=anthropic-...
GOOGLE_API_KEY=...
GEMINI_MODEL_NAME=gemini-2.5-pro
UPSTAGE_API_KEY=...

# Database
DATABASE_URL=postgresql://finuser:finpass@fin-postgres:5432/financial

# Vector DB / Cache
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379

# Optional
SENTRY_DSN=...
CERT_PATH=/etc/ssl/certs/ca-certificates.crt
```

> 민감 정보(API Key 등)는 **절대 Git에 커밋하지 마세요.**  
> `.env.example` 파일로 키 이름만 공유하는 것을 권장합니다.

---

## 6️⃣ Docker 빌드 & 이미지 최적화

### ✅ 최적화된 Dockerfile

멀티 스테이지 빌드로 빌더/런타임를 분리하여 이미지 용량을 크게 줄였습니다.

```dockerfile
# ====== RUNTIME BASE ======
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     libpq5     && rm -rf /var/lib/apt/lists/*

# ====== BUILDER ======
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     libpq-dev     && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ====== FINAL RUNTIME ======
FROM base AS final

WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# uv 대신 venv의 python 직접 실행
CMD ["/app/.venv/bin/python", "main.py"]
```

### ✅ .dockerignore

루트에 `.dockerignore` 파일을 생성합니다.

```dockerignore
.git
__pycache__
*.pyc
*.log
.venv
experiments/
tests/
notebooks/
```

### 빌드 & 확인

```bash
docker build -t fin-agent-app .
docker images
```

`fin-agent-app` 이미지의 CONTENT SIZE가 ~400–700MB 정도면 정상입니다.

---

## 7️⃣ Oracle Cloud(OCI) 배포 가이드

### 7-1. Docker 설치 (Oracle Linux 9)

```bash
sudo dnf update -y
sudo dnf install -y docker
sudo systemctl enable docker
sudo systemctl start docker

# opc 사용자가 docker 사용 가능하도록
sudo usermod -aG docker opc
# 로그아웃 후 재접속 필요
```

---

### 7-2. 프로젝트 배포

```bash
cd ~
git clone http://YOUR_GIT_SERVER/SG-OHIA-2025-TEAM-03/financial-strategy-agent.git
cd financial-strategy-agent
```

> 실제 저장소 URL/디렉터리는 환경에 맞게 수정하세요.

---

### 7-3. Docker 네트워크 & PostgreSQL

```bash
docker network create fin-net

docker run -d   --name fin-postgres   --network fin-net   -e POSTGRES_USER=finuser   -e POSTGRES_PASSWORD=finpass   -e POSTGRES_DB=financial   --restart unless-stopped   postgres:16
```

---

### 7-4. 앱 컨테이너 실행

```bash
docker run -d   --name fin-agent-app   --network fin-net   -p 8000:8000   --env-file .env   --restart unless-stopped   fin-agent-app
```

확인:

```bash
docker ps
curl http://localhost:8000
```

---

### 7-5. 초기 데이터 시드 (jobs)

```bash
# 종목 마스터
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin/python -m jobs.seed_companies

# 가격 데이터
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin/python -m jobs.load_prices_daily

# 신호/지표 계산
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin/python -m jobs.calc_signals_latest
```

---

## 8️⃣ Cloudflare Tunnel (무료 HTTPS)

### 8-1. cloudflared 설치 (ARM64)

```bash
cd ~
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/cloudflared

cloudflared --version
```

---

### 8-2. Quick Tunnel 실행 (nohup)

```bash
nohup /usr/local/bin/cloudflared tunnel --url http://localhost:8000 > cloudflared.log 2>&1 &
tail -f cloudflared.log
```

로그에서 다음과 같은 라인을 찾습니다.

```text
Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):
https://xxxxx-something.trycloudflare.com
```

이 주소가 외부에서 접근 가능한 HTTPS 엔드포인트입니다.

> Quick Tunnel은 **재실행 시 주소가 변경**될 수 있습니다.  
> 고정 도메인이 필요하다면 Cloudflare에서 도메인/Named Tunnel을 사용하는 구성이 필요합니다.

---

## 9️⃣ 배치 작업 / Cron Jobs

### 9-1. 작업 스케줄 (KST)

| 작업                | 시간 (KST) | 설명                                |
|---------------------|-----------:|-------------------------------------|
| `load_prices_daily` | 15:40      | 장 마감 후 일별 시세 로드          |
| `calc_signals_latest` | 15:40    | 최신 기술적 지표 계산               |
| `load_fundamentals` | 01:00      | 재무제표/펀더멘털 데이터 업데이트  |

OCI 서버는 UTC 기준이므로, KST(+9)를 UTC로 변환해야 합니다.

- 15:40 KST → 06:40 UTC
- 01:00 KST → 16:00 UTC

---

### 9-2. Shell 스크립트 예시

`/home/opc/jobs/daily.sh`:

```bash
#!/bin/bash
cd /home/opc/financial-strategy-agent

echo "[JOB] load_prices_daily"
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin/python -m jobs.load_prices_daily

echo "[JOB] calc_signals_latest"
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin/python -m jobs.calc_signals_latest
```

`/home/opc/jobs/fundamentals.sh`:

```bash
#!/bin/bash
cd /home/opc/financial-strategy-agent

echo "[JOB] load_fundamentals"
docker run --rm --network fin-net --env-file .env fin-agent-app   /app/.venv/bin.python -m jobs.load_fundamentals
```

권한 부여:

```bash
chmod +x /home/opc/jobs/daily.sh
chmod +x /home/opc/jobs/fundamentals.sh
```

---

### 9-3. 크론 등록 (UTC 기준)

```bash
crontab -e
```

아래 내용 추가:

```cron
# 주가 / 기술 지표 (06:40 UTC = 15:40 KST)
40 6 * * *  bash /home/opc/jobs/daily.sh >> /home/opc/cron.log 2>&1

# 재무제표 (16:00 UTC = 01:00 KST)
0 16 * * *  bash /home/opc/jobs/fundamentals.sh >> /home/opc/cron.log 2>&1
```

---

## 🔟 핵심 API 레퍼런스

아래는 `main.py`에 정의된 주요 엔드포인트 요약입니다.  
실제 파라미터/응답 구조는 코드와 OpenAPI(/docs) 참조.

### 기본 페이지

- `GET /` → `templates/index.html`
- `GET /portfolio` → 포트폴리오 분석 UI
- `GET /stock` → 단일 종목 분석 UI

### 메타 데이터

- `GET /api/sectors` → 사용 가능한 섹터 목록
- `GET /api/stocks` → 사용 가능한 종목 목록
- `GET /api/models` → 사용 가능한 LLM 모델 목록

### 포트폴리오 분석

- `POST /api/analyze/anthropic`
- `POST /api/analyze/langgraph`

예시 요청:

```powershell
$body = @{
  budget = 1000000
  investment_targets = @{ sectors = @('IT'); tickers = @('005930.KS') }
  risk_profile = '중립'
  investment_period = '중기'
  model_name = 'solar-pro2'
  additional_prompt = ''
} | ConvertTo-Json -Depth 5

curl -X POST "http://localhost:8000/api/analyze/anthropic" `
  -H "Content-Type: application/json" `
  -d $body
```

### 종목 단일 분석

- `POST /api/stock/anthropic`
- `POST /api/stock/langgraph`

Body 예시:

```json
{
  "ticker": "005930.KS",
  "profile": "balanced",
  "model_name": "gpt-4o-mini"
}
```

### 보조 엔드포인트 (예시)

- `GET /api/quick-info/{ticker}`
- `GET /api/chart-data/{ticker}`
- `GET /api/sector-comparison/{ticker}`

---

## 1️⃣1️⃣ 프론트엔드 & PDF 생성(Playwright)

### PDF 생성 흐름

1. 프론트엔드에서 현재 리포트 HTML을 직렬화  
2. 서버 `/api/stock/download-pdf` 혹은 `/api/download-pdf`에 POST  
3. FastAPI + Playwright가 HTML 로드 후 `page.pdf()`로 생성  
4. `StreamingResponse`로 PDF 다운로드 응답 반환  

### 모바일(iOS / WebView) 문제와 해결

일반적인 `fetch → blob → a.download` 방식은 모바일에서 잘 안 될 수 있습니다.  
보다 안정적인 방식:

```javascript
const form = document.createElement('form');
form.method = 'POST';
form.action = '/api/stock/download-pdf';
form.target = '_blank';
form.style.display = 'none';

const input = document.createElement('input');
input.name = 'html';
input.value = htmlContent; // 서버에서 처리 가능한 크기로 제한
form.appendChild(input);

document.body.appendChild(form);
form.submit();
form.remove();
```

또는:

- 서버에서 PDF를 생성 후 파일 URL 반환
- 프론트엔드에서 `window.open(url)` 또는 `<a href="...">`로 브라우저 네이티브 다운로드 유도

---

## 1️⃣2️⃣ 문제 해결(FAQ)

### Q1. 컨테이너 실행 시 `exec: "uv": executable file not found in $PATH`

- 원인: 최적화 Dockerfile의 final 스테이지에 `uv` CLI가 포함되어 있지 않음  
- 해결: `CMD ["uv", "run", "python", "main.py"]` 대신  
  `CMD ["/app/.venv/bin/python", "main.py"]` 사용 (현재 README의 Dockerfile이 이미 반영)

---

### Q2. Cloudflare Tunnel 로그에 `Cannot determine default origin certificate path` 에러

- Quick Tunnel 모드에서 흔히 보이는 경고 수준 메시지  
- Named Tunnel + Origin 인증서 사용 시 필요하며, **Quick Tunnel에서는 무시 가능**

---

### Q3. Cloudflare Tunnel 주소가 재실행 때마다 바뀜

- Quick Tunnel의 특성상 URL이 고정되지 않습니다.  
- 고정 도메인이 필요하다면:
  - 도메인을 구입 후 Cloudflare에 등록  
  - Named Tunnel + CNAME 설정으로 고정 URL 구성

---

### Q4. yfinance / 외부 API에서 SSL 오류

- `CERT_PATH` 환경 변수를 사용하거나  
- OS의 CA 인증서 패키지 설치/갱신 필요  
- `main.py`에서 인증서 경로를 읽어 처리하는 부분 참고

---

## 1️⃣3️⃣ 기여 / 라이선스 / 연락처

- 이슈/PR 환영  
- 코드 변경 시:
  - 테스트 코드 작성/수정 권장 (`pytest`)
  - 린트/포맷팅 도구 사용 (`ruff`, `black` 등)

라이선스와 기여 규칙은 팀/조직 정책에 따라 `LICENSE`, `CONTRIBUTING.md`에 명시하는 것을 권장합니다.

---

## 1️⃣4️⃣ 변경 기록

- **v0.2.0**
  - Oracle Cloud(OCI) + Docker + PostgreSQL + Cloudflare Tunnel 기반 실제 운영 구조 문서화
  - 최적화된 Dockerfile 및 이미지 사이즈 축소 (2.7GB → 442MB)
  - 배치 작업(Cron) 및 Seed 작업 플로우 추가
  - PDF 생성/모바일 대응 가이드 추가

- **v0.1.0**
  - 초기 README 작성
  - 로컬 개발/실행 가이드 추가

---

# sector-portfolio-agent

Investment AI Agent Building
