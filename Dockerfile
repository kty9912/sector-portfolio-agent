# ====== RUNTIME BASE (최종 실행 단계) ======
FROM python:3.11-slim AS base

# Python 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 작업 디렉토리
WORKDIR /app

# 런타임에 필요한 패키지
# PDF 생성용 chromium은 Playwright가 설치함
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*


# ====== BUILDER (빌드 전용 단계) ======
FROM python:3.11-slim AS builder

WORKDIR /app

# 빌드에 필요한 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 메타 파일
COPY pyproject.toml uv.lock ./

# 가상환경 + 의존성 설치
RUN uv sync --frozen --no-dev


# ====== FINAL STAGE ======
FROM python:3.11-slim AS final

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 런타임 필요한 패키지 + Playwright chromium 의존성
# playwright 브라우저가 실행되기 위해 필요한 system deps 포함
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    wget \
    libnss3 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

# builder 단계에서 만들어진 venv 복사
COPY --from=builder /app/.venv ./.venv

# 소스 복사
COPY . .

# PATH 설정
ENV PATH="/app/.venv/bin:$PATH"

# 🔥 Playwright 브라우저 설치 (PDF 렌더링 위해 반드시 필요)
# ➜ 딱 1번만 실행되며 Docker image layer로 캐싱됨!
RUN playwright install --with-deps chromium

EXPOSE 8000

CMD ["/app/.venv/bin/python", "main.py"]
