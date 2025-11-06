import os
from fastapi import FastAPI, Query, HTTPException, Request
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import List, Dict, Any

# --- [Main] .env 파일 로드 (가장 먼저 실행!) ---
# 'core'나 'agents' 모듈이 임포트되기 *전에* .env를 로드해야 합니다.
load_dotenv()
print("--- [Main] .env 파일 로드 완료 ---")

# --- [Main] 핵심 모듈 임포트 ---
# .env 로드 이후에 임포트해야, 이 모듈들이 API 키를 올바르게 읽을 수 있습니다.
from langchain_core.messages import HumanMessage # HumanMessage 임포트 추가
try:
    # 이 임포트가 성공하려면, 
    # 1. 'core/graph_builder.py' 파일이 완전해야 하고
    # 2. 'core/llm_clients.py' 파일이 완전해야 합니다.
    from core.graph_builder import compiled_engine_map
    from core.llm_clients import AVAILABLE_MODELS
except ImportError as e:
    print("\n==================================================")
    print(f"!!! 핵심 모듈 임포트 실패: {e}")
    print("!!! 'core/graph_builder.py' 또는 'core/llm_clients.py' 파일에 문제가 없는지 확인하세요.")
    print("!!! (uv sync --extra dev를 실행했는지도 확인하세요)")
    print("==================================================")
    compiled_engine_map = {} # 서버가 일단 켜지도록 비워둡니다.
    AVAILABLE_MODELS = [] # 서버가 일단 켜지도록 비워둡니다.
except Exception as e:
    print(f"\n!!! 알 수 없는 임포트 에러 발생: {e}")
    compiled_engine_map = {}
    AVAILABLE_MODELS = []


# --- [FastAPI] Lifespan (시작/종료 이벤트) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버가 시작될 때 실행
    print("\n--- [FastAPI Startup] 서버 시작... ---")
    
    # 1. 'AVAILABLE_MODELS' (전체 목록)을 FastAPI 앱 상태에 저장
    app.state.ALL_MODELS_LIST = AVAILABLE_MODELS
    
    # 2. 'compiled_engine_map' (실제로 로드된 엔진)을 앱 상태에 저장
    app.state.LOADED_ENGINE_MAP = compiled_engine_map
    app.state.LOADED_MODELS_LIST = list(compiled_engine_map.keys())
    
    print(f"--- [FastAPI Startup] ★실제로 로드된★ 모델: {app.state.LOADED_MODELS_LIST} ---")
    
    yield
    
    # 서버가 종료될 때 실행
    print("\n--- [FastAPI Shutdown] 서버 종료... ---")

# --- [FastAPI] 앱 생성 ---
app = FastAPI(
    title="Sector Portfolio Agent API",
    description="AI-powered sector portfolio generator (LangGraph Engine)",
    version="1.0.0",
    lifespan=lifespan
)

# --- [FastAPI] API 엔드포인트 ---
@app.post(
    "/generate-portfolio-v1", 
    summary="Generate Portfolio (V1 - LangGraph)",
    description="(V1) LangGraph 엔진을 사용하여 섹터 포트폴리오 분석을 실행합니다."
)
async def generate_portfolio_v1(
    request: Request,
    sector_name: str = Query(
        ..., 
        description="분석할 섹터 이름 (예: 반도체, 바이오)",
        examples=["반도체", "AI"]
    ),
    model: str = Query(
        # ★★★ 여기가 드롭다운을 만드는 핵심입니다 ★★★
        # FastAPI가 시작될 때 'AVAILABLE_MODELS' (전체 목록)을 읽어서 'enum'을 동적으로 생성합니다.
        ..., 
        enum=AVAILABLE_MODELS, # <- AVAILABLE_MODELS(API 키가 있든 없든)로 enum을 *정의*합니다.
        description="사용할 LLM 모델을 선택하세요."
    )
):
    """
    LangGraph 엔진을 호출하여 섹터 분석을 수행합니다.
    """
    print(f"\n--- [FastAPI Request] '/generate-portfolio-v1' 호출됨 ---")
    print(f"  > Sector: {sector_name}")
    print(f"  > Model: {model}")

    # 1. 'LOADED_MODELS_LIST' (API 키가 실제로 있는 모델)에 사용자가 요청한 모델이 있는지 확인합니다.
    if model not in request.app.state.LOADED_MODELS_LIST:
        print(f"  > !!! 에러: '{model}' 모델은 사용 가능하지 않습니다. (.env 파일에 API 키를 확인하세요)")
        raise HTTPException(
            status_code=400, 
            detail=f"'{model}' 모델은 현재 사용 가능하지 않습니다. 서버 .env 파일에 API 키가 등록되었는지 확인하세요."
        )

    # 2. 올바른 엔진(컴파일된 그래프)을 맵에서 선택합니다.
    compiled_engine = request.app.state.LOADED_ENGINE_MAP[model]

    # 3. LangGraph 엔진 실행
    try:
        # LangGraph는 비동기(ainvoke)로 호출합니다.
        initial_state = {
            "sector_name": sector_name,
            "messages": [HumanMessage(content=f"'{sector_name}' 섹터를 분석해줘.")],
            "iteration_count": 0
        }
        
        # .ainvoke()는 최종 상태(final_state)를 반환합니다.
        final_state = await compiled_engine.ainvoke(initial_state)
        
        # 4. 최종 결과 반환
        report = final_state.get("final_report", "오류: 최종 보고서를 생성하지 못했습니다.")
        print(f"  > 분석 완료. 보고서 반환.")
        return {"sector": sector_name, "model": model, "final_report": report}

    except Exception as e:
        print(f"  > !!! LangGraph 엔진 실행 중 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=f"엔진 실행 중 오류 발생: {e}")

# (Uvicorn으로 실행하기 위한 엔트리 포인트)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

