import os
import uuid
from typing import List, Dict
from datetime import datetime

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


# # --- 2. 감성분석기 임포트 ---
# try:
#     from agents.sentiment_analyzer import sentiment_analyzer
#     print("--- [Tools] 감성분석기 로드 완료 ---")
# except ImportError:
#     print("--- [Tools] 경고: 'agents/sentiment_analyzer.py' 파일을 찾을 수 없습니다. 감성분석 비활성화 ---")
#     sentiment_analyzer = None


# API 키 및 클라이언트 초기화 ---
# FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# firecrawl_client = None
# if FIRECRAWL_API_KEY:
#     firecrawl_client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
#     print("--- [Tools] Firecrawl 클라이언트 초기화 완료 ---")
# else:
#     print("--- [Tools] 경고: FIRECRAWL_API_KEY가 .env에 없습니다. 'ingest_news_qdrant' 툴이 실패합니다. ---")

# --- 3. 임베딩 모델 변경: multilingual-e5-large ---
print("\n--- [Tools] 임베딩 모델 로드 중... ---")
# ⭐ 변경: all-MiniLM-L6-v2 (384차원) → multilingual-e5-large (1024차원)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')
EMBEDDING_DIMENSION = 1024  # ⭐ 384 → 1024
COLLECTION_NAME = "sector_news_v2"  # ⭐ 새 컬렉션 이름
print(f"--- [Tools] 임베딩 모델 로딩 완료: multilingual-e5-large ({EMBEDDING_DIMENSION}차원) ---")

# --- 4. 출처 신뢰도 맵 ---
SOURCE_TRUST_MAP = {
    "samsung.com": 0.95,      # 증권사 리서치
    "miraeasset.com": 0.95,
    "hankyung.com": 0.85,     # 경제 전문지
    "mk.co.kr": 0.85,
    "naver.com": 0.70,        # 포털 뉴스
    "daum.net": 0.70,
}

def get_trust_score(url: str) -> float:
    """URL에서 도메인 추출 후 신뢰도 점수 반환"""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        domain = domain.replace('www.', '')
        return SOURCE_TRUST_MAP.get(domain, 0.6)  # 기본값 0.6
    except:
        return 0.6

# --- 5. 툴 정의 (총 3개) ---
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
        tavily_tool = TavilySearchResults(max_results=10, tavily_api_key=TAVILY_API_KEY)
        results = tavily_tool.invoke(query)
        print(f"[Agent 5 Tool - Tavily] 실시간 검색 완료. {len(results)}개 결과 반환.")
        return results # (이미 요약된 내용과 출처 URL이 포함된 dict 리스트)
    except Exception as e:
        return [{"error": str(e)}]

@tool
def search_sector_news_qdrant(sector_name: str) -> dict:
    """
    ⭐ 변경: Firecrawl 제거, 순수 Qdrant 검색만
    
    (Agent 5 - 장기 기억) 
    Qdrant DB에 이미 저장된 49,605개의 뉴스 중에서
    'sector_name'과 가장 관련성 높은 뉴스를 검색합니다.
    1단계: Qdrant에서 상위 100개 검색
    2단계: 감성/신뢰도로 필터링 → 최종 10개만 LLM에게 전달
    """
    print(f"\n[Agent 5 Tool - Qdrant] 섹터 뉴스 검색 시작: '{sector_name}'")
    
    try:
        # --- 1. 검색 쿼리 생성 (더 정교하게) ---
        # E5 모델은 "query: " 접두사를 붙이면 검색 품질이 향상됩니다
        query_text = f"query: {sector_name} 섹터의 최근 동향과 투자 전망 분석"
        query_vector = embedding_model.encode(query_text).tolist()
        
        # --- 2. Qdrant 검색 (필터 + 스코어 임계값) ---
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=100,
            # # ⭐ 필터 추가 (선택적 - 신뢰도 높은 뉴스만)
            # query_filter=models.Filter(
            #     must=[
            #         models.FieldCondition(
            #             key="sentiment_confidence",
            #             range=models.Range(gte=0.5)  # 신뢰도 50% 이상
            #         )
            #     ]
            # ),
            score_threshold=0.5  # 유사도 50% 이상만 반환
        )
        
        # --- 3. 결과 정리 ---
        results = []
        for res in search_results:
            payload = res.payload
            # 신뢰도 점수 계산
            sentiment_conf = payload.get('sentiment_confidence', 0.0)
            source_trust = get_trust_score(payload.get('source_url', ''))
            
            # 종합 점수 = 유사도 * 0.5 + 감성신뢰도 * 0.3 + 출처신뢰도 * 0.2
            combined_score = (
                res.score * 0.5 + 
                sentiment_conf * 0.3 + 
                source_trust * 0.2
            )
            
            results.append({
                "combined_score": combined_score,
                "similarity_score": res.score,
                "title": payload.get('title', '')[:80],  # ⭐ 제목 축약
                "sentiment": payload.get('sentiment', 'neutral'),
                "sentiment_score": payload.get('sentiment_score', 0.0),
                "sentiment_confidence": sentiment_conf,
                "source": payload.get('source_domain', ''),
                "published_at": payload.get('published_at', '')[:10],
                "text_preview": payload.get('text', '')[:150] + "..."  # ⭐ 150자만
            })
        
        print(f"  > [Qdrant] 검색 완료: {len(results)}개 결과")
        
        # 종합 점수로 정렬 후 상위 10개만
        results.sort(key=lambda x: x['combined_score'], reverse=True)
        results = results[:10]  # ⭐ 최종 10개

        # --- 4. 감성 통계 계산 (추가) ---
        if results:
            sentiment_stats = {
                "positive": sum(1 for r in results if r['sentiment'] == 'positive'),
                "neutral": sum(1 for r in results if r['sentiment'] == 'neutral'),
                "negative": sum(1 for r in results if r['sentiment'] == 'negative'),
                "avg_sentiment_score": round(
                    sum(r['sentiment_score'] for r in results) / len(results), 3
                ),
                "avg_confidence": round(
                        sum(r['sentiment_confidence'] for r in results) / len(results), 3
                    )
            }
        else:
            sentiment_stats = {
                "positive": 0, "neutral": 0, "negative": 0,
                "avg_sentiment_score": 0.0, "avg_confidence": 0.0
            }
            
        return {
            "query": sector_name,
            "total_results": len(results),
            "sentiment_stats": sentiment_stats,
            "news": results
            }
        
    except Exception as e:
        print(f"  > !!! Qdrant 검색 에러: {e}")
        return {"error": str(e)}

# --- 6. 툴 리스트 ---
available_tools = [
    get_sector_etf_momentum,
    search_realtime_news_tavily,
    search_sector_news_qdrant
]

# --- Qdrant 컬렉션 확인 (초기화 X) ---
def _check_qdrant_collection():
    """
    ⭐ 변경: 컬렉션 생성 안함 (이미 49,605개 데이터 존재)
    존재 여부만 확인
    """
    print("\n--- [Tools] Qdrant 컬렉션 확인... ---")
    try:
        collection_info = qdrant_client.get_collection(collection_name=COLLECTION_NAME)
        point_count = collection_info.points_count
        print(f"✅ '{COLLECTION_NAME}' 컬렉션 확인 완료")
        print(f"   저장된 뉴스 개수: {point_count:,}개")
        print(f"   벡터 차원: {EMBEDDING_DIMENSION}")
    except Exception as e:
        print(f"❌ 컬렉션 확인 실패: {e}")
        print("   → Qdrant URL/API Key를 .env에서 확인하세요.")

_check_qdrant_collection()