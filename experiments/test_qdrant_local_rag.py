# 1. 라이브러리 임포트
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import uuid # 고유 ID 생성을 위해
import os

def run_local_rag_test():
    """
    API 키 없이 Qdrant와 로컬 임베딩 모델을 사용한
    RAG 파이프라인 핵심 로직 실험
    """
    print("--- 로컬 RAG 실험 시작 ---")

    # --- 준비 단계 ---
    
    # 2. 로컬 임베딩 모델 로드 (OpenAI 대신 사용)
    # (주의: 이 모델은 한국어를 지원하는 모델입니다. 처음 실행 시 수백MB를 다운로드합니다.)
    print("로컬 임베딩 모델 로딩 중... (최초 1회 시간이 걸릴 수 있습니다)")
    # 다국어 지원 모델 (한국어 포함)
    encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    # 임베딩 벡터의 차원(dimension)을 확인
    vector_dim = encoder.get_sentence_embedding_dimension()
    print(f"모델 로드 완료. 벡터 차원: {vector_dim}")

    # 3. Qdrant 클라이언트 초기화 (in-memory: 디스크 저장 없이 메모리에서만 실행)
    # (가장 빠르고 간편한 테스트 방식입니다)
    client = QdrantClient(":memory:")
    print("Qdrant (in-memory) 클라이언트 초기화 완료.")

    # 4. Qdrant에 'Collection' (우리만의 뉴스 저장소) 생성
    collection_name = "my_news_vectors"
    try:
        client.recreate_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_dim,  # 위에서 확인한 임베딩 모델의 차원
                distance=models.Distance.COSINE # 코사인 유사도 (의미 기반 검색에 표준)
            )
        )
        print(f"'{collection_name}' 컬렉션 생성 완료.")
    except Exception as e:
        print(f"컬렉션 생성 실패: {e}")
        return

    # --- 1. [수집] 단계 (Firecrawl API 대신 가짜 뉴스 데이터 사용) ---
    print("\n--- 1. [수집] 단계 (가짜 뉴스 데이터) ---")
    
    # 가짜 뉴스 데이터 (출처, 본문)
    fake_news_data = [
        {"source": "news.com/1", "sector": "반도체", "content": "NVIDIA가 HBM4 개발에 성공하며 AI 칩 시장의 리더십을 공고히 했습니다. 삼성전자와 SK하이닉스도 경쟁에 뛰어들고 있습니다."},
        {"source": "econ.com/2", "sector": "바이오", "content": "FDA가 새로운 비만 치료제 승인을 보류하면서, 관련 제약사들의 주가가 일제히 하락했습니다. 임상 데이터 보완이 요구됩니다."},
        {"source": "tech.com/3", "sector": "방위산업", "content": "K-방산, 폴란드에 이어 중동 지역 대규모 수출 계약 체결. 현대로템과 한화에어로스페이스의 실적 기대감이 커집니다."},
        {"source":"it.com/4", "sector": "AI", "content": "오픈AI의 차세대 모델 GPT-5가 공개되면서, 관련 AI 소프트웨어 및 서비스 기업들에 대한 투자 심리가 긍정적입니다."}
    ]
    print(f"{len(fake_news_data)}개의 가짜 뉴스 데이터 준비 완료.")

    # --- 2. [임베딩] & 3. [Qdrant 저장] 단계 ---
    print("\n--- 2 & 3. [임베딩] 및 [Qdrant 저장] 단계 ---")
    
    points_to_upsert = []
    for news in fake_news_data:
        # 2. [임베딩]: 뉴스 본문을 로컬 모델을 사용해 벡터로 변환
        vector = encoder.encode(news["content"]).tolist()
        
        # 3. [저장 준비]: Qdrant에 저장할 데이터(Point) 생성
        #    - id: 고유 식별자
        #    - vector: 임베딩된 벡터
        #    - payload: 검색 시 함께 반환될 원본 데이터 (메타데이터)
        points_to_upsert.append(
            models.PointStruct(
                id=str(uuid.uuid4()), # 랜덤 고유 ID 생성
                vector=vector,
                payload={
                    "original_text": news["content"],
                    "source": news["source"],
                    "sector": news["sector"]
                }
            )
        )
        print(f"'{news['sector']}' 섹터 뉴스 임베딩 완료.")

    # 3. [Qdrant 저장]: 준비된 데이터를 Qdrant에 한 번에 업로드 (Upsert)
    client.upsert(
        collection_name=collection_name,
        points=points_to_upsert
    )
    print(f"\n총 {len(points_to_upsert)}개의 뉴스 벡터를 Qdrant에 저장 완료!")

    # --- 4. [검색] 단계 (RAG의 핵심) ---
    print("\n--- 4. [검색] 단계 (의미 기반 검색) ---")
    
    # 검색 쿼리
    search_query = "AI 칩 시장의 최신 동향은?"
    print(f"검색 쿼리: \"{search_query}\"")

    # 쿼리 임베딩: 검색 쿼리도 '동일한' 로컬 모델로 벡터로 변환
    query_vector = encoder.encode(search_query).tolist()
    print("검색 쿼리 임베딩 완료.")

    # Qdrant 검색 실행
    # (저장된 벡터 중, 쿼리 벡터와 코사인 유사도가 가장 높은 상위 2개 검색)
    search_results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=2 # 가장 유사한 2개만
    )
    
    print("\n[검색 결과]")
    for i, result in enumerate(search_results):
        print(f"  [유사도 {i+1}위 / 점수: {result.score:.4f}]")
        print(f"  > 원본: {result.payload['original_text']}")
        print(f"  > 출처: {result.payload['source']}\n")

    print("--- 로컬 RAG 실험 종료 ---")

# 이 스크립트를 직접 실행할 수 있도록 설정
if __name__ == "__main__":
    run_local_rag_test()
