FROM python:3.11-slim

# 컨테이너 안에서 사용할 작업 디렉토리
WORKDIR /app

# 시스템 패키지 (PostgreSQL 드라이버 빌드 등에 필요할 수 있음)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 메타 파일 먼저 복사
COPY pyproject.toml uv.lock ./

# uv로 의존성 설치 (프로젝트용 가상환경 자동 생성)
RUN uv sync --frozen --no-dev

# 👉 Playwright 브라우저(Chromium) + 필요한 시스템 deps 설치
# uv가 만든 venv는 /app/.venv 이라서, 그 안의 playwright 바이너리를 직접 실행
RUN /app/.venv/bin/playwright install --with-deps chromium

# 나머지 코드 전부 복사
COPY . .

# 로그 flush
ENV PYTHONUNBUFFERED=1

# 웹 서비스 포트
EXPOSE 8000

# 앱 실행 (현재 main.py가 엔트리라고 가정)
CMD ["uv", "run", "python", "main.py"]