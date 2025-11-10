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


# --- 2. 감성분석기 임포트 ---
try:
    from agents.sentiment_analyzer import sentiment_analyzer
    print("--- [Tools] 감성분석기 로드 완료 ---")
except ImportError:
    print("--- [Tools] 경고: 'agents/sentiment_analyzer.py' 파일을 찾을 수 없습니다. 감성분석 비활성화 ---")
    sentiment_analyzer = None


# API 키 및 클라이언트 초기화 ---
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

firecrawl_client = None
if FIRECRAWL_API_KEY:
    firecrawl_client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    print("--- [Tools] Firecrawl 클라이언트 초기화 완료 ---")
else:
    print("--- [Tools] 경고: FIRECRAWL_API_KEY가 .env에 없습니다. 'ingest_news_qdrant' 툴이 실패합니다. ---")

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
    ⭐ 수정된 함수: FinBERT 감성분석 + 개선된 Qdrant 스키마
    
    (Agent 5 - 장기 기억) 
    1. Firecrawl로 'sector_name' 키워드 뉴스 수집
    2. FinBERT-KR로 감성분석
    3. 풍부한 메타데이터와 함께 Qdrant DB에 저장
    4. Qdrant DB에서 'sector_name'과 가장 관련성 높은 뉴스 검색
    """
    print(f"\n[Agent 5 Tool - Qdrant/Firecrawl] 장기 기억 RAG 시작. 섹터: '{sector_name}'")
    
    # --- 1. 수집(Ingest) ---
    if not firecrawl_client:
        return {"error": "Firecrawl 클라이언트가 초기화되지 않았습니다. (.env 키 확인)"}
    
    try:
        print(f"  > [Firecrawl] '{sector_name}' 섹터 뉴스 크롤링 시도...")
        # Firecrawl의 search는 SearchData 객체를 반환합니다.
        search_data = firecrawl_client.search(
            query=f"{sector_name} 섹터 뉴스 한국",
            scrape_options={
                "max_results": 10,
                "country": "kr",
                "time_range": "1y"
            }
        )
        
        # SearchData 객체에서 web 결과를 추출하여 Qdrant 포인트로 변환
        # 뉴스 데이터 추출
        news_list = []
        web_results = search_data.web if hasattr(search_data, 'web') else []

        for item in web_results:
            description = item.description if hasattr(item, 'description') else ''
            if description and len(description) > 50:  # 너무 짧은 설명은 제외
                news_list.append({
                    "text": description,
                    "title": item.title if hasattr(item, 'title') else '',
                    "url": item.url if hasattr(item, 'url') else ''
                })
        
        if not news_list:
             print("  > [Firecrawl] 크롤링된 뉴스가 없거나 유효하지 않습니다.")
             return {"error": "Firecrawl에서 유효한 뉴스를 수집하지 못했습니다."}
        
        print(f"  > [Firecrawl] {len(news_list)}개 뉴스 수집 완료")

        # --- 2. 감성분석 (FinBERT 하이브리드) ---
        if sentiment_analyzer:
            print(f" > [FinBERT] 감성분석 시작...")
            analyzed_news = sentiment_analyzer.analyze_batch(news_list)
        else:
            print("  > [경고] 감성분석기 비활성화. 기본값 사용")
            analyzed_news = news_list

        # --- 3. Qdrant 저장 (개선된 스키마) ---
        print(f"  > [Qdrant] 벡터 DB 저장 시작...")
        points_to_upsert = []
        
        for news in analyzed_news:
            # 임베딩 생성 (원본 텍스트 전체)
            vector = embedding_model.encode(news['text']).tolist()
            
            # ⭐ 개선된 Payload 스키마
            payload = {
                # 핵심 필드
                "text": news['text'],           # 원본 전체
                "title": news.get('title', ''),
                "sector": sector_name,
                
                # 감성분석 (FinBERT)
                "sentiment": news.get('sentiment', 'neutral'),
                "sentiment_score": news.get('sentiment_score', 0.0),
                "sentiment_confidence": news.get('sentiment_confidence', 0.0),
                "analysis_method": news.get('method', 'none'),
                
                # 출처 신뢰도
                "source_url": news.get('url', ''),
                "source_domain": news.get('url', '').split('/')[2] if '/' in news.get('url', '') else '',
                "source_trust_score": get_trust_score(news.get('url', '')),
                
                # 시간 정보
                "published_at": datetime.now().isoformat(),
                "crawled_at": datetime.now().isoformat(),
                
                # 중복 방지
                "content_hash": str(uuid.uuid4()),  # 실제론 MD5(title+date)
                
                # 추가 메타
                "companies": [],  # TODO: NER로 기업명 추출
                "tags": [],       # TODO: 키워드 추출
            }
            
            points_to_upsert.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
        
        # Qdrant upsert
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert
        )
        print(f"  > [Qdrant] {len(points_to_upsert)}개 뉴스 저장 완료")

    except Exception as e:
        print(f"  > !!! Firecrawl/Qdrant 수집 단계 에러: {e}")
        return {"error": str(e)}

    # --- 4. 검색(Search) ---
    try:
        query_vector = embedding_model.encode(f"{sector_name} 섹터의 전반적인 동향과 투자 전망").tolist()
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=5,  # ⭐ 3 → 5로 증가
            # ⭐ 필터 추가 (선택)
            # query_filter=models.Filter(
            #     must=[
            #         models.FieldCondition(
            #             key="sentiment_confidence",
            #             range=models.Range(gte=0.5)
            #         )
            #     ]
            # )
        )
        
        results = [
            {
                "score": res.score,
                "payload": res.payload,
                # 주요 정보만 추출 (LLM에게 전달)
                "summary": {
                    "title": res.payload.get('title', ''),
                    "sentiment": res.payload.get('sentiment', 'neutral'),
                    "sentiment_score": res.payload.get('sentiment_score', 0.0),
                    "source": res.payload.get('source_domain', ''),
                    "text_preview": res.payload.get('text', '')[:200] + "..."
                }
            }
            for res in search_results
        ]
        
        print(f"  > [Qdrant] RAG 검색 완료. {len(results)}개 결과 반환.")
        return {"query": sector_name, "results": results}
        
    except Exception as e:
        print(f"  > !!! Qdrant 검색 단계 에러: {e}")
        return {"error": str(e)}

# --- 6. 툴 리스트 ---
available_tools = [
    get_sector_etf_momentum,
    search_realtime_news_tavily,
    ingest_and_search_qdrant
]

# --- 7. Qdrant 컬렉션 초기화 (새 스키마) ---
def _initialize_qdrant_collection():
    """
    ⭐ 수정: multilingual-e5-large (1024차원) 컬렉션 생성
    기존 'sector_news_rag' 컬렉션은 무시하고 'sector_news_v2'만 관리
    """
    print("\n--- [Tools] Qdrant 컬렉션 초기화 시도... ---")
    try:
        # 컬렉션이 존재하는지 확인 (존재하지 않으면 에러 발생)
        try:
            qdrant_client.get_collection(collection_name=COLLECTION_NAME)
            print(f"✅ '{COLLECTION_NAME}' 컬렉션이 이미 존재합니다. (1024차원)")
        except Exception:
            print(f"📦 '{COLLECTION_NAME}' 컬렉션이 없습니다. 새로 생성합니다... (1024차원)")
            qdrant_client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,  # 1024
                    distance=Distance.COSINE
                )
            )
            
            # ⭐ Payload 인덱스 생성 (필터링 성능)
            print(f"  > Payload 인덱스 생성 중...")
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="sector",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="sentiment",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            
            print(f"✅ '{COLLECTION_NAME}' 컬렉션 생성 완료 ({EMBEDDING_DIMENSION}차원)")

    except Exception as e:
        print(f"--- [Tools] !!! Qdrant 컬렉션 초기화 중 에러: {e} ---")

# ⭐ 컬렉션 초기화 실행
_initialize_qdrant_collection()

# ⭐ 기존 컬렉션 정리 안내 (선택)
try:
    old_collections = qdrant_client.get_collections().collections
    old_names = [c.name for c in old_collections if c.name != COLLECTION_NAME]
    if old_names:
        print(f"\n💡 참고: 기존 컬렉션 발견 {old_names}")
        print(f"   삭제하려면: python -c \"from core.vector_db import qdrant_client; qdrant_client.delete_collection('{old_names[0]}')\"")
except:
    pass