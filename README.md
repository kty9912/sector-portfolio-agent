document.body.appendChild(form);

# Sector Portfolio Agent (간단판)

간단한 소개

AI 기반 섹터/종목 분석 및 포트폴리오 구성 연구용 프로젝트입니다. FastAPI 백엔드와 몇 가지 LLM 클라이언트(OpenAI/Anthropic 등)를 사용하며, Docker로 컨테이너화해 배포할 수 있습니다.

핵심: 로컬 개발 빠른 시작(Quickstart), 환경변수(.env)로 API 키 관리, Docker 이미지로 배포.

## 빠른 시작 (Quickstart)

Windows 개발(예)

1) 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) 의존성 설치

```powershell
python -m pip install --upgrade pip
pip install -e .
```

3) 개발 서버 실행

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

브라우저: http://localhost:8000

## 환경 변수

프로젝트 루트에 `.env` 파일을 만들되, 실제 키는 절대 저장소에 커밋하지 마세요. 대신 `.env.example`에 필요한 키 이름만 둡니다.

예시(`.env.example`에 넣을 내용):

```
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
DATABASE_URL=postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DBNAME>
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
```

.gitignore에 `.env`가 포함되어 있는지 확인하세요(현재 포함되어 있음).

## Docker (요약)

빌드:

```powershell
docker build -t fin-agent-app .
```

실행(권장: 비밀 관리는 Docker secrets 또는 클라우드 시크릿 매니저 사용):

```powershell
docker run -d --name fin-agent-app -p 8000:8000 --env-file .env --restart unless-stopped fin-agent-app
```

컨테이너에서 프로덕션으로 서비스를 운용할 때는 `uvicorn`/`gunicorn` CLI로 앱을 실행하는 것을 권장합니다. 예:

```powershell
# 개발
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션(예)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

설명: README 내에 `uv`(일부 환경에서 dependency sync/lock을 위한 도구로 사용됨) 관련 내용이 혼재되어 있어 혼동이 발생했습니다. 이 프로젝트에서 런타임으로는 `uvicorn`을 사용하고 있으며, `uv` CLI는 선택적(의존성 동기화)입니다. 따라서 README에서는 `uv` 사용을 선택적 섹션으로 분리하거나 제거하는 것이 명확합니다.

## 간단한 배치/잡 실행

직접 실행(로컬 또는 컨테이너 내부):

```powershell
python -m jobs.seed_companies
python -m jobs.load_prices_daily
python -m jobs.calc_signals_latest
```

Docker에서 실행할 때는 `/app/.venv/bin/python -m jobs.<name>` 형식으로 실행하도록 이미지를 구성해 두었습니다.

## 보안 체크리스트 (중요)

- README나 코드에 민감한 값(실제 API 키, DB 비밀번호)을 남기지 마세요. 항상 placeholder 사용.
- `.env`는 버전관리에서 제외되어야 합니다(.gitignore에 추가되어 있음).
- 로그에 API 키나 전체 토큰을 출력하지 마세요. (예: `core/llm_clients.py`의 `print` 디버그 상태를 로거의 debug로 변경 권장)
- 배포 환경에서는 Docker secrets, Kubernetes Secrets, 또는 클라우드 제공자의 Secret Manager 사용을 권장합니다.
- 만약 키가 깃에 유출되었다면 즉시 회수(rotate)하세요.

## `uv` / `uvicorn` 관련 요약

- `uvicorn`은 ASGI 서버로 개발 및 프로덕션에서 흔히 사용됩니다.
- `uv`는 (이 레포에 존재하는) 잠금/동기화 도구로 보이며, 런타임 서버 역할을 하는 것은 아닙니다. `uv` 관련 명령을 사용하려면 문서에 "선택적"으로만 기재하세요.
- 권장 실행 방식: CLI(`uvicorn ...`)로 실행하거나, 컨테이너에서 `gunicorn -k uvicorn.workers.UvicornWorker`를 사용하는 것이 일반적입니다.

## 기여 및 라이선스

- 이슈/PR 환영합니다. 코드 변경 시 테스트 추가를 권장합니다.
- 라이선스/기여 규칙은 `LICENSE`, `CONTRIBUTING.md`에 별도 기재하세요.

## 변경 기록 (요약)

- v0.2.0: OCI+Docker 배포 문서화, 이미지 최적화, 배치 작업 추가
- v0.1.0: 초기 작성

---

간단 정리본을 적용했습니다. 자세한 원본 문서는 필요 시 보존하거나, README에 "상세 가이드" 링크로 연결하는 것을 권장합니다.
