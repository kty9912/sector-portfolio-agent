import yfinance as yf
import pandas as pd
from langchain_core.tools import tool
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import uuid

# --- Agent 2: 데이터 분석가 툴 ---

SECTOR_ETF_MAP = {
    "반도체": "SOXX", "AI": "BOTZ", "바이오": "XBI",
    "방위산업": "PPA", "블록체인": "BLOK"
}

@tool
def get_sector_etf_momentum(sector_name: str) -> dict:
    """
    (Agent 2) yfinance를 사용해 섹터 ETF의 모멘텀(50일 이평선)을 계산합니다.
    LangGraph가 이 툴을 호출합니다.
    """
    print(f"\n--- [Tool] Agent 2: 데이터 분석가 Tool 실행: {sector_name} ---")
    ticker = SECTOR_ETF_MAP.get(sector_name)
    if not ticker:
        return {"error": "Sector ETF not found"}
    try:
        data = yf.download(ticker, period="3mo", progress=False)
        if data.empty:
            return {"error": f"No data found for {ticker}"}
            
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        latest_close = data['Close'].iloc[-1]
        latest_sma = data['SMA_50'].iloc[-1]
        momentum_signal = "Positive" if latest_close > latest_sma else "Negative"
        
        return {
            "ticker": ticker,
            "latest_close": round(latest_close, 2),
            "sma_50": round(latest_sma, 2),
            "momentum_signal": momentum_signal
        }
    except Exception as e:
        return {"error": str(e)}

# --- Agent 5: 뉴스 분석가 (RAG) 툴 ---

# 1. 로컬 임베딩 모델 (API 키 불필요)
# (이 모델은 프로그램 시작 시 한 번만 로드됩니다.)
print("--- [Tool] 로컬 임베딩 모델 로딩 중... (최초 1회) ---")
encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
vector_dim = encoder.get_sentence_embedding_dimension()
print("--- [Tool] 로컬 임베딩 모델 로드 완료 ---")

# 2. 로컬 Qdrant 클라이언트 (API 키 불필요)
# (실험용 :memory: 모드를 사용합니다.)
qdrant_client = QdrantClient(":memory:")
qdrant_client.recreate_collection(
    collection_name="sector_news",
    vectors_config=models.VectorParams(size=vector_dim, distance=models.Distance.COSINE)
)

# 3. (임시) Qdrant에 가짜 데이터 미리 채우기
# (원래 이 단계는 Firecrawl이 매일 밤 수행해야 합니다)
print("--- [Tool] Qdrant DB에 임시 데이터 저장 중... ---")
fake_news_data = [
    {"sector": "반도체", "content": "NVIDIA가 HBM4 개발에 성공하며 AI 칩 시장의 리더십을 공고히 했습니다. 삼성전자와 SK하이닉스도 경쟁에 뛰어들고 있습니다."},
    {"sector": "바이오", "content": "FDA가 새로운 비만 치료제 승인을 보류하면서, 관련 제약사들의 주가가 일제히 하락했습니다."},
    {"sector": "방위산업", "content": "K-방산, 중동 지역 대규모 수출 계약 체결. 현대로템과 한화에어로스페이스의 실적 기대감이 커집니다."}
]
points_to_upsert = []
for news in fake_news_data:
    vector = encoder.encode(news["content"]).tolist()
    points_to_upsert.append(
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"original_text": news["content"], "sector": news["sector"]}
        )
    )
qdrant_client.upsert(collection_name="sector_news", points=points_to_upsert)
print("--- [Tool] Qdrant DB 임시 데이터 저장 완료 ---")


@tool
def search_sector_news_rag(sector_name: str) -> dict:
    """
    (Agent 5) Qdrant와 로컬 임베딩을 사용해 RAG로 뉴스 심리를 분석합니다.
    LangGraph가 이 툴을 호출합니다.
    """
    print(f"\n--- [Tool] Agent 5: 뉴스 RAG Tool 실행: {sector_name} ---")
    try:
        # 1. 검색 쿼리 생성 (섹터 이름 자체를 쿼리로 사용)
        query_vector = encoder.encode(sector_name).tolist()
        
        # 2. Qdrant 검색
        search_results = qdrant_client.search(
            collection_name="sector_news",
            query_vector=query_vector,
            limit=1 # 가장 유사한 뉴스 1개만
        )
        
        if not search_results:
            return {"error": "Relevant news not found in Qdrant DB"}

        top_result = search_results[0]
        
        # 3. 간단한 심리 판단 (여기서 Upstage LLM을 또 호출할 수도 있습니다)
        # (간단한 예시로, '하락'이 포함되면 부정적으로 판단)
        content = top_result.payload['original_text']
        sentiment = "Negative" if "하락" in content else "Positive"
        
        return {
            "retrieved_news": content,
            "sentiment": sentiment,
            "score": top_result.score
        }
    except Exception as e:
        return {"error": str(e)}

# LangGraph가 사용할 툴 리스트
available_tools = [get_sector_etf_momentum, search_sector_news_rag]
