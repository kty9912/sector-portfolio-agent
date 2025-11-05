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

