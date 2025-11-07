# agents/sentiment_analyzer.py
"""
FinBERT-KR 기반 하이브리드 감성분석기
GPU 있으면 FinBERT, 없으면 사전 기반 + LLM fallback
"""

import os
import hashlib
import json
from pathlib import Path
from typing import Dict, List
import torch

# GPU 체크
HAS_GPU = torch.cuda.is_available()
print(f"\n--- [Sentiment Analyzer] GPU 감지: {'✅ CUDA 사용 가능' if HAS_GPU else '❌ CPU 모드'} ---")


# ============================================
# 1. 사전 기반 감성분석 (CPU Fallback)
# ============================================

FINANCIAL_SENTIMENT_LEXICON = {
    "positive": {
        # 실적/성장
        "상승": 1.0, "증가": 1.0, "성장": 1.0, "확대": 0.8,
        "호조": 1.2, "개선": 1.0, "회복": 1.0, "반등": 1.0,
        "급증": 1.5, "폭증": 1.5, "급등": 1.5, "최대": 1.2,
        "최고": 1.2, "신고가": 1.5, "사상최대": 1.5,
        "호실적": 1.5, "어닝서프라이즈": 1.8,
        
        # 재무
        "흑자": 1.5, "흑자전환": 2.0, "영업이익증가": 1.5,
        "순이익증가": 1.5, "배당": 0.8, "배당증가": 1.2,
        
        # 시장
        "수주": 1.0, "대규모수주": 1.5, "계약체결": 1.0,
        "점유율증가": 1.2, "점유율확대": 1.2,
        
        # 기술
        "신제품출시": 1.0, "양산": 1.2, "특허": 0.8,
        "혁신": 1.0, "세계최초": 1.5,
    },
    "negative": {
        # 실적/성장
        "하락": -1.0, "감소": -1.0, "부진": -1.2, "악화": -1.2,
        "둔화": -0.8, "위축": -1.0, "급락": -1.5, "폭락": -1.5,
        "최저": -1.2, "최악": -1.5, "실적부진": -1.5,
        "어닝쇼크": -1.8, "어닝미스": -1.5,
        
        # 재무
        "적자": -1.5, "적자전환": -2.0, "영업손실": -1.5,
        "순손실": -1.5, "부채증가": -1.0,
        
        # 리스크
        "규제": -1.0, "제재": -1.5, "과징금": -1.2,
        "소송": -1.0, "리콜": -1.5, "결함": -1.2,
        "중단": -1.2, "가동중단": -1.5,
        
        # 시장
        "점유율하락": -1.2, "경쟁심화": -0.8,
        "철수": -1.5, "구조조정": -1.2,
    }
}


def analyze_with_lexicon(text: str) -> Dict:
    """사전 기반 감성분석 (초고속, CPU)"""
    positive_score = 0.0
    negative_score = 0.0
    matched_pos = []
    matched_neg = []
    
    for keyword, weight in FINANCIAL_SENTIMENT_LEXICON["positive"].items():
        if keyword in text:
            positive_score += weight
            matched_pos.append(keyword)
    
    for keyword, weight in FINANCIAL_SENTIMENT_LEXICON["negative"].items():
        if keyword in text:
            negative_score += abs(weight)
            matched_neg.append(keyword)
    
    total_matches = len(matched_pos) + len(matched_neg)
    
    if total_matches == 0:
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "sentiment_confidence": 0.0,
            "method": "lexicon",
            "details": {"matched_positive": [], "matched_negative": []}
        }
    
    net_score = positive_score - negative_score
    normalized_score = net_score / (positive_score + negative_score)
    
    if normalized_score > 0.15:
        sentiment = "positive"
    elif normalized_score < -0.15:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    
    confidence = min(total_matches / 10, 0.95)
    
    return {
        "sentiment": sentiment,
        "sentiment_score": normalized_score,
        "sentiment_confidence": confidence,
        "method": "lexicon",
        "details": {
            "matched_positive": matched_pos,
            "matched_negative": matched_neg
        }
    }


# ============================================
# 2. FinBERT-KR (GPU/CPU 자동 선택)
# ============================================

class FinBERTAnalyzer:
    """
    FinBERT-KR 감성분석기 (GPU/CPU 자동 선택)
    """
    
    def __init__(self):
        self.model_name = "snunlp/KR-FinBert-SC"
        self.device = "cuda" if HAS_GPU else "cpu"
        self.cache_dir = Path("./cache/finbert")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "sentiment_cache.json"
        self.cache = self._load_cache()
        
        print(f"\n--- [FinBERT] 모델 로딩 ({self.device.upper()}) ---")
        
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            
            # CPU 최적화
            if self.device == "cpu":
                torch.set_num_threads(4)
                print("  > CPU 최적화 활성화 (4 threads)")
            
            print(f"  > FinBERT-KR 로딩 완료 ({self.device.upper()})")
            self.available = True
            
        except Exception as e:
            print(f"  > ⚠️ FinBERT-KR 로딩 실패: {e}")
            print("  > 사전 기반 + LLM fallback으로 동작합니다.")
            self.available = False
    
    def _load_cache(self) -> Dict:
        """캐시 로드"""
        if self.cache_file.exists():
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_cache(self):
        """캐시 저장"""
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def _get_cache_key(self, text: str) -> str:
        """텍스트 해시"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def analyze(self, text: str) -> Dict:
        """단일 뉴스 감성분석 (캐싱 포함)"""
        if not self.available:
            # FinBERT 사용 불가 시 사전 기반
            return analyze_with_lexicon(text)
        
        # 캐시 체크
        cache_key = self._get_cache_key(text)
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # FinBERT 추론
        try:
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
            
            probs = torch.nn.functional.softmax(logits, dim=-1)
            scores = probs[0].cpu().tolist()
            
            labels = ["negative", "neutral", "positive"]
            predicted_idx = scores.index(max(scores))
            predicted = labels[predicted_idx]
            
            result = {
                "sentiment": predicted,
                "sentiment_score": scores[predicted_idx],
                "sentiment_confidence": scores[predicted_idx],
                "method": "finbert-kr",
                "scores": {label: score for label, score in zip(labels, scores)}
            }
            
            # 캐시 저장
            self.cache[cache_key] = result
            self._save_cache()
            
            return result
            
        except Exception as e:
            print(f"  > FinBERT 추론 에러: {e}")
            return analyze_with_lexicon(text)
    
    def analyze_batch(self, texts: List[str], batch_size: int = 8) -> List[Dict]:
        """배치 분석 (속도 최적화)"""
        if not self.available:
            return [analyze_with_lexicon(t) for t in texts]
        
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            
            # 캐시된 결과 먼저 체크
            batch_results = []
            texts_to_process = []
            indices_to_process = []
            
            for idx, text in enumerate(batch):
                cache_key = self._get_cache_key(text)
                if cache_key in self.cache:
                    batch_results.append(self.cache[cache_key])
                else:
                    texts_to_process.append(text)
                    indices_to_process.append(idx)
                    batch_results.append(None)  # 나중에 채움
            
            # 캐시 미스만 처리
            if texts_to_process:
                try:
                    inputs = self.tokenizer(
                        texts_to_process,
                        return_tensors="pt",
                        truncation=True,
                        max_length=512,
                        padding=True
                    ).to(self.device)
                    
                    with torch.no_grad():
                        outputs = self.model(**inputs)
                        logits = outputs.logits
                    
                    probs = torch.nn.functional.softmax(logits, dim=-1)
                    
                    labels = ["negative", "neutral", "positive"]
                    for j, prob in enumerate(probs):
                        scores = prob.cpu().tolist()
                        predicted_idx = scores.index(max(scores))
                        
                        result = {
                            "sentiment": labels[predicted_idx],
                            "sentiment_score": scores[predicted_idx],
                            "sentiment_confidence": scores[predicted_idx],
                            "method": "finbert-kr",
                            "scores": {label: score for label, score in zip(labels, scores)}
                        }
                        
                        # 캐시 저장
                        cache_key = self._get_cache_key(texts_to_process[j])
                        self.cache[cache_key] = result
                        
                        # 결과 삽입
                        original_idx = indices_to_process[j]
                        batch_results[original_idx] = result
                    
                    self._save_cache()
                    
                except Exception as e:
                    print(f"  > 배치 처리 에러: {e}")
                    for idx in indices_to_process:
                        if batch_results[idx] is None:
                            batch_results[idx] = analyze_with_lexicon(batch[idx])
            
            results.extend(batch_results)
        
        return results


# ============================================
# 3. 하이브리드 분석기 (전략 통합)
# ============================================

class HybridSentimentAnalyzer:
    """
    하이브리드 감성분석 전략
    
    1차: 사전 기반 (전체 뉴스, 0.001초)
    2차: FinBERT (신뢰도 낮은 뉴스만) 또는 LLM (선택)
    """
    
    def __init__(self, llm_client=None):
        self.finbert = FinBERTAnalyzer()
        self.llm_client = llm_client
    
    def analyze_batch(self, news_list: List[Dict]) -> List[Dict]:
        """
        스마트 배치 분석
        
        Args:
            news_list: [{"text": "...", "title": "..."}, ...]
        
        Returns:
            [{"text": "...", "sentiment": "...", ...}, ...]
        """
        print(f"\n=== [Hybrid] 감성분석 시작 ({len(news_list)}개 뉴스) ===")
        
        # 1차: 사전 기반 (전체)
        print("  [1단계] 사전 기반 필터링...")
        results = []
        refinement_candidates = []
        
        for idx, news in enumerate(news_list):
            lexicon_result = analyze_with_lexicon(news['text'])
            
            # 신뢰도 낮으면 FinBERT 재분석 대기열
            if lexicon_result['sentiment_confidence'] < 0.6:
                refinement_candidates.append((idx, news))
                results.append(None)  # 나중에 채움
            else:
                results.append({**news, **lexicon_result})
        
        print(f"    완료: {len(news_list) - len(refinement_candidates)}개 확정, {len(refinement_candidates)}개 재분석 필요")
        
        # 2차: FinBERT (선별)
        if refinement_candidates and self.finbert.available:
            print(f"  [2단계] FinBERT 재분석 ({len(refinement_candidates)}개)...")
            
            candidate_texts = [news['text'] for _, news in refinement_candidates]
            finbert_results = self.finbert.analyze_batch(candidate_texts, batch_size=8)
            
            for (idx, news), finbert_result in zip(refinement_candidates, finbert_results):
                results[idx] = {**news, **finbert_result}
            
            print(f"    완료")
        
        # 3차: LLM fallback (선택, FinBERT 없을 때)
        elif refinement_candidates and self.llm_client:
            print(f"  [2단계] LLM fallback ({len(refinement_candidates)}개)...")
            # LLM 구현은 선택 (필요시)
            for idx, news in refinement_candidates:
                if results[idx] is None:
                    results[idx] = {**news, **analyze_with_lexicon(news['text'])}
        
        print(f"=== [Hybrid] 감성분석 완료 ===\n")
        return results


# ============================================
# 싱글톤 인스턴스 생성
# ============================================

print("\n--- [Sentiment Analyzer] 초기화 시작 ---")
sentiment_analyzer = HybridSentimentAnalyzer()
print("--- [Sentiment Analyzer] 초기화 완료 ---")