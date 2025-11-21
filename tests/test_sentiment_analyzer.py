import pytest
from agents.sentiment_analyzer import analyze_with_lexicon, HybridSentimentAnalyzer

def test_analyze_with_lexicon_positive():
    result = analyze_with_lexicon("상승 성장 호조")
    assert result["sentiment"] == "positive"

def test_analyze_with_lexicon_negative():
    result = analyze_with_lexicon("하락 부진 악화")
    assert result["sentiment"] == "negative"

def test_hybrid_sentiment_analyzer_batch():
    analyzer = HybridSentimentAnalyzer()
    news_list = [{"text": "상승 성장 호조", "title": "테스트"}]
    results = analyzer.analyze_batch(news_list)
    assert isinstance(results, list)
    assert "sentiment" in results[0]
