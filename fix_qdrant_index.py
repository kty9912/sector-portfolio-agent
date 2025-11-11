# scripts/fix_qdrant_index.py (새 파일 생성)

"""
Qdrant 컬렉션에 Payload 인덱스 추가
(필터링 성능 향상 + 에러 해결)
"""

from core.vector_db import qdrant_client
from qdrant_client.http import models

COLLECTION_NAME = "sector_news_v2"

def create_payload_indexes():
    """필수 인덱스 생성"""
    
    print(f"\n{'='*50}")
    print(f"Qdrant '{COLLECTION_NAME}' 인덱스 생성 시작")
    print('='*50)
    
    indexes_to_create = [
        # 1. sentiment_confidence (float 타입)
        {
            "field_name": "sentiment_confidence",
            "field_schema": models.PayloadSchemaType.FLOAT
        },
        # 2. sentiment (keyword 타입)
        {
            "field_name": "sentiment",
            "field_schema": models.PayloadSchemaType.KEYWORD
        },
        # 3. sector (keyword 타입)
        {
            "field_name": "sector",
            "field_schema": models.PayloadSchemaType.KEYWORD
        },
        # 4. published_at (datetime 타입)
        {
            "field_name": "published_at",
            "field_schema": models.PayloadSchemaType.DATETIME
        }
    ]
    
    for idx_config in indexes_to_create:
        try:
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                **idx_config
            )
            print(f"✅ 인덱스 생성 완료: {idx_config['field_name']} ({idx_config['field_schema']})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"⏭️  이미 존재: {idx_config['field_name']}")
            else:
                print(f"❌ 생성 실패: {idx_config['field_name']} - {e}")
    
    print(f"\n{'='*50}")
    print("인덱스 생성 완료!")
    print('='*50)

if __name__ == "__main__":
    create_payload_indexes()