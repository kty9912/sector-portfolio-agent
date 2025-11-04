import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# .env 파일 로드 (llm_clients.py에서도 하지만, 여기서도 해주는 것이 안전함)
load_dotenv()

def get_qdrant_client():
    """
    .env 파일의 환경 변수를 읽어 Qdrant 클라이언트를 생성하는 팩토리 함수.
    
    - .env에 QDRANT_URL과 QDRANT_API_KEY가 있으면 -> Qdrant Cloud에 연결
    - 없으면 -> 로컬 :memory: 모드 (테스트용)
    """
    
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if qdrant_url and qdrant_api_key:
        # --- 1. 프로덕션/클라우드 모드 ---
        print("\n--- [Qdrant Factory] Qdrant Cloud 모드로 연결합니다. ---")
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key
        )
    else:
        # --- 2. 로컬/테스트 모드 ---
        print("\n--- [Qdrant Factory] .env에 Qdrant 정보가 없습니다. 로컬 :memory: 모드로 실행합니다. ---")
        client = QdrantClient(":memory:")

    return client

# --- 싱글톤(Singleton) 패턴 ---
# FastAPI 서버가 실행되는 동안 Qdrant 클라이언트는 '단 하나'만 생성해서 공유합니다.
# (API가 호출될 때마다 매번 새로 연결하는 것은 매우 비효율적)
qdrant_client = get_qdrant_client()
