# 한 번만 실행 (10GB 정도 다운로드)
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
# Embedding 모델
print('Downloading multilingual-e5-large...')
SentenceTransformer('intfloat/multilingual-e5-large')

# FinBERT 모델
print('Downloading KR-FinBert-SC...')
AutoTokenizer.from_pretrained('snunlp/KR-FinBert-SC')
AutoModelForSequenceClassification.from_pretrained('snunlp/KR-FinBert-SC')

print('Done!')