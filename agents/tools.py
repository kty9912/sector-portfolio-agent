import os
import uuid
from typing import List, Dict

from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from sentence_transformers import SentenceTransformer
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams
from firecrawl import FirecrawlApp
import yfinance as yf
import pandas as pd

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

# API 키 및 클라이언트 초기화 ---
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

firecrawl_client = None
if FIRECRAWL_API_KEY:
    firecrawl_client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    print("--- [Tools] Firecrawl 클라이언트 초기화 완료 ---")
else:
    print("--- [Tools] 경고: FIRECRAWL_API_KEY가 .env에 없습니다. 'ingest_news_qdrant' 툴이 실패합니다. ---")

# --- 2. 임베딩 모델 (로컬) Qdrant ---
print("\n--- [Tools] 로컬 임베딩 모델(SentenceTransformer) 로드 중... ---")
# 'all-MiniLM-L6-v2'는 384차원의 벡터를 생성합니다.
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
EMBEDDING_DIMENSION = 384 
COLLECTION_NAME = "sector_news_rag"

# --- 3. 툴 정의 (총 3개) ---
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

@tool
def search_realtime_news_tavily(query: str) -> List[Dict]:
    """
    (Agent 5 - 단기 기억) Tavily를 사용해 '지금 이 순간'의 최신 뉴스를 
    검색하고 요약합니다. "최신 속보"나 "오늘 동향"에 사용합니다.
    """
    print(f"\n[Agent 5 Tool - Tavily] 실시간 검색 시작. 쿼리: '{query}'")
    if not TAVILY_API_KEY:
        return [{"error": "TAVILY_API_KEY가 .env에 없습니다."}]
    
    try:
        tavily_tool = TavilySearchResults(max_results=3, tavily_api_key=TAVILY_API_KEY)
        results = tavily_tool.invoke(query)
        print(f"[Agent 5 Tool - Tavily] 실시간 검색 완료. {len(results)}개 결과 반환.")
        return results # (이미 요약된 내용과 출처 URL이 포함된 dict 리스트)
    except Exception as e:
        return [{"error": str(e)}]

# 4. 뉴스 수집 저장 검색 
@tool
def ingest_and_search_qdrant(sector_name: str) -> dict:
    """
    (Agent 5 - 장기 기억) 1. Firecrawl로 'sector_name' 키워드 뉴스를 
    수집(JSON)하여 Qdrant DB에 '저장(Ingest)'합니다.
    2. Qdrant DB에서 'sector_name'과 가장 관련성 높은 뉴스를 '검색(Search)'합니다.
    "지난 얼마 기간의 동향"이나 "깊이 있는 분석"에 사용합니다.
    """
    print(f"\n[Agent 5 Tool - Qdrant/Firecrawl] 장기 기억 RAG 시작. 섹터: '{sector_name}'")
    
    # --- 1. 수집(Ingest) ---
    if not firecrawl_client:
        return {"error": "Firecrawl 클라이언트가 초기화되지 않았습니다. (.env 키 확인)"}
    
    try:
        print(f"  > [Firecrawl] '{sector_name}' 섹터 뉴스 3개 크롤링 시도...")
        # Firecrawl의 search는 SearchData 객체를 반환합니다.
        search_data = firecrawl_client.search(
            query=f"{sector_name} 섹터 뉴스",
            scrape_options={
                "max_results": 3,
                "country": "kr",
                "time_range": "1y"
            }
        )
        
        # SearchData 객체에서 web 결과를 추출하여 Qdrant 포인트로 변환
        points_to_upsert = []
        web_results = search_data.web if hasattr(search_data, 'web') else []
        for item in web_results:
            description = item.description if hasattr(item, 'description') else ''
            if description and len(description) > 50:  # 너무 짧은 설명은 제외
                vector = embedding_model.encode(description).tolist()
                payload = {
                    "text": description,
                    "source": item.url if hasattr(item, 'url') else '',
                    "title": item.title if hasattr(item, 'title') else ''
                }
                # Qdrant의 ID는 URL 해시 등으로 고유하게 만드는 것이 좋음
                points_to_upsert.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()), # 지금은 임시로 랜덤 ID
                        vector=vector,
                        payload=payload
                    )
                )
        
        if not points_to_upsert:
             print("  > [Firecrawl] 크롤링된 뉴스가 없거나 유효하지 않습니다.")
             return {"error": "Firecrawl에서 유효한 뉴스를 수집하지 못했습니다."}

        # Qdrant에 실시간 저장 (upsert = 덮어쓰기/삽입)
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert
        )
        print(f"  > [Qdrant] {len(points_to_upsert)}개의 새 뉴스를 DB에 저장 완료.")

    except Exception as e:
        print(f"  > !!! Firecrawl/Qdrant 수집 단계 에러: {e}")
        return {"error": str(e)}

    # --- 2. 검색(Search) ---
    try:
        query_vector = embedding_model.encode(f"{sector_name} 섹터의 전반적인 동향").tolist()
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=3
        )
        
        results = [{"score": res.score, "payload": res.payload} for res in search_results]
        print(f"  > [Qdrant] RAG 검색 완료. {len(results)}개 결과 반환.")
        return {"query": sector_name, "results": results}
        
    except Exception as e:
        print(f"  > !!! Qdrant 검색 단계 에러: {e}")
        return {"error": str(e)}

# --- 5. 툴 리스트 ---
available_tools = [
    get_sector_etf_momentum,
    search_realtime_news_tavily,
    ingest_and_search_qdrant
]

# --- 6. (임시) Qdrant 컬렉션 생성 ---
def _initialize_qdrant_collection():
    """
    서버 시작 시 Qdrant 컬렉션이 없으면 생성
    """
    print("\n--- [Tools] Qdrant 컬렉션 초기화 시도... ---")
    try:
        # 컬렉션이 존재하는지 확인 (존재하지 않으면 에러 발생)
        try:
            qdrant_client.get_collection(collection_name=COLLECTION_NAME)
            print(f"'{COLLECTION_NAME}' 컬렉션이 이미 존재합니다. 초기화 건너뜀.")
        except Exception:
            # 컬렉션이 없으므로 새로 생성
            print(f"'{COLLECTION_NAME}' 컬렉션이 없습니다. 새로 생성합니다.")
            qdrant_client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
            )
            print(f"'{COLLECTION_NAME}' 컬렉션 생성 완료. (차원: {EMBEDDING_DIMENSION})")

    except Exception as e:
        print(f"--- [Tools] !!! Qdrant 컬렉션 초기화 중 에러: {e} ---")

_initialize_qdrant_collection()
