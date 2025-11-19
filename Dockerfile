# ====== RUNTIME BASE (최종 실행 단계) ======
FROM python:3.11-slim AS base

# Python 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 작업 디렉토리
WORKDIR /app

# 런타임에 필요한 최소 패키지
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
FROM base AS final

WORKDIR /app

# builder 단계에서 만든 가상환경 복사
COPY --from=builder /app/.venv ./.venv

# 전체 소스 복사
COPY . .

# PATH 지정
ENV PATH="/app/.venv/bin:$PATH"

# 서비스 포트
EXPOSE 8000

# FastAPI 실행
CMD ["uv", "run", "python", "main.py"]
