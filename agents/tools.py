from langchain_core.tools import tool
import yfinance as yf
import pandas as pd
from sentence_transformers import SentenceTransformer

# --- 1. Qdrant 팩토리에서 '공유 클라이언트' 임포트 ---
# (이 코드가 작동하려면 core/vector_db.py 파일이 반드시 필요합니다)
try:
    from core.vector_db import qdrant_client 
except ImportError:
    print("!!! 에러: 'core/vector_db.py' 파일을 찾을 수 없습니다. 먼저 생성해주세요. !!!")
    # 임시 방편으로 :memory: 모드 사용
    from qdrant_client import QdrantClient
    qdrant_client = QdrantClient(":memory:")
    print("--- [Tools] 경고: 'core.vector_db'를 찾지 못해 임시 :memory: 모드로 실행합니다. ---")


# --- 2. 임베딩 모델 (로컬) ---
print("\n--- [Tools] 로컬 임베딩 모델(SentenceTransformer) 로드 중... ---")
# 'all-MiniLM-L6-v2'는 384차원의 벡터를 생성합니다.
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
EMBEDDING_DIMENSION = 384 
COLLECTION_NAME = "sector_news_rag"

# --- 3. yfinance 툴 (Agent 2) ---
@tool
def get_sector_etf_momentum(sector_name: str) -> dict:
    """
    (Agent 2) yfinance를 사용해 섹터 ETF의 기본 모멘텀(예: 50일 이평선)을 계산합니다.
    """
    print(f"\n[Agent 2 Tool] '{sector_name}' 모멘텀 분석 시작...")
    
    # (임시) 실제로는 섹터명 <-> ETF 티커 매핑 필요
    SECTOR_ETF_MAP = { 
        "반도체": "SOXX", 
        "바이오": "XBI", 
        "AI": "BOTZ",
        "방위산업": "PPA",
        "블록체인": "BLOK"
    }
    ticker = SECTOR_ETF_MAP.get(sector_name, "SPY") # 기본값 SPY
    
    try:
        data = yf.download(ticker, period="3mo", progress=False)
        if data.empty:
            return {"error": f"No data found for {ticker}"}
            
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        latest_close = data['Close'].iloc[-1]
        latest_sma = data['SMA_50'].iloc[-1]
        momentum_signal = "Positive" if latest_close > latest_sma else "Negative"
        
        print(f"[Agent 2 Tool] '{sector_name}' 모멘텀 분석 완료.")
        return {
            "ticker": ticker,
            "latest_close": round(latest_close, 2),
            "sma_50": round(latest_sma, 2),
            "momentum_signal": momentum_signal
        }
    except Exception as e:
        return {"error": str(e)}

# --- 4. Qdrant RAG 툴 (Agent 5) ---
@tool
def search_sector_news_rag(query: str) -> dict:
    """
    (Agent 5) Qdrant 벡터 DB에서 'query'와 가장 유사한 뉴스를 검색합니다.
    """
    print(f"\n[Agent 5 Tool] Qdrant RAG 검색 시작. 쿼리: '{query}'")
    
    try:
        # 1. 쿼리를 벡터로 변환
        query_vector = embedding_model.encode(query).tolist()
        
        # 2. Qdrant DB에 검색
        # (qdrant_client는 core/vector_db.py에서 가져온 '싱글톤' 클라이언트)
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=3, # 상위 3개 결과만
            with_payload=True # 저장된 원본 데이터(뉴스 본문)도 함께 가져오기
        )
        
        # 3. 결과 파싱
        results = []
        for result in search_results:
            results.append({
                "score": result.score,
                "text": result.payload.get("text"),
                "source": result.payload.get("source")
            })
            
        print(f"[Agent 5 Tool] RAG 검색 완료. {len(results)}개 결과 반환.")
        return {"query": query, "results": results}

    except Exception as e:
        # (컬렉션이 아직 없는 등) 에러 처리
        print(f"[Agent 5 Tool] RAG 검색 중 에러: {e}")
        # .env 파일에 QDRANT_URL/API_KEY가 없어서 :memory: 모드일 때,
        # _temp_ingest_fake_data_to_qdrant()가 실행되지 않으면 컬렉션이 없어 에러가 날 수 있음.
        return {"error": str(e), "message": f"'{COLLECTION_NAME}' 컬렉션이 없거나 Qdrant에 연결할 수 없습니다. (데이터 수집 단계가 필요할 수 있음)"}

# --- 5. 툴 리스트 ---
# (이 리스트는 core/graph_builder.py에서 사용됩니다)
available_tools = [get_sector_etf_momentum, search_sector_news_rag]

# --- 6. (임시) 데이터 수집/저장 함수 ---
def _temp_ingest_fake_data_to_qdrant():
    """
    (임시 테스트용) 서버 시작 시 Qdrant에 가짜 데이터를 저장하는 함수
    """
    print("\n--- [Tools] (임시) Qdrant에 테스트 데이터 저장 시도... ---")
    try:
        from qdrant_client.http.models import Distance, VectorParams, PointStruct

        # 1. 컬렉션 (테이블) 생성 (차원 수, 유사도 방식 지정)
        qdrant_client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
        )
        print(f"'{COLLECTION_NAME}' 컬렉션 생성 완료. (차원: {EMBEDDING_DIMENSION})")

        # 2. 가짜 뉴스 데이터
        fake_news_data = [
            {"source": "news.com/1", "text": "NVIDIA가 HBM4 개발에 성공하며 AI 칩 시장의 리더십을 공고히 했습니다."},
            {"source": "econ.com/2", "text": "미국 FDA, 신규 당뇨병 치료제(GLP-1)의 신속 승인을 발표. 바이오 섹터 전반에 긍정적."},
            {"source": "defense.com/3", "text": "한국, 폴란드에 10조원 규모 2차 방산 수출 계약 체결. K-방산 신뢰도 급상승."},
            {"source": "it.com/4", "text": "오픈AI의 차세대 모델 GPT-5가 공개되면서, 관련 AI 소프트웨어 기업들에 대한 투자 심리가 긍정적입니다."}
        ]
        
        # 3. 데이터 임베딩 및 Qdrant Point 생성
        points_to_upsert = []
        for i, news in enumerate(fake_news_data):
            points_to_upsert.append(
                PointStruct(
                    id=i + 1, # 고유 ID
                    vector=embedding_model.encode(news["text"]).tolist(), # 벡터
                    payload=news # 원본 데이터
                )
            )
        
        # 4. Qdrant에 저장 (upsert = 덮어쓰기)
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert,
            wait=True
        )
        print(f"총 {len(points_to_upsert)}개의 테스트 데이터를 Qdrant에 저장 완료.")

    except Exception as e:
        print(f"--- [Tools] (임시) Qdrant 데이터 저장 중 에러 (이미 존재할 수 있음): {e} ---")

# 이 파일(agents/tools.py)이 처음 임포트될 때, 
# (즉, uvicorn 서버가 켜질 때)
# Qdrant에 임시 데이터를 한 번 저장합니다.
_temp_ingest_fake_data_to_qdrant()

