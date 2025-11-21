import pytest
from agents import stock_agent_anthropic

# DB, 외부 API, LLM 모킹 예시
class DummyLLM:
    def invoke(self, *args, **kwargs):
        class DummyResponse:
            content = '''```json
            {"meta": {"generated_at": "2025-11-20", "ticker": "005930.KS", "profile": "balanced"},
             "basic_info": {"ticker": "005930.KS", "name_kr": "삼성전자", "market": "KOSPI", "industry": "반도체", "market_cap_level": "대형주", "summary_sentence": "테스트"},
             "market_snapshot": {"current_price": 70000, "price_change_1d": 0.01, "return_1m": 0.05, "return_3m": 0.10, "return_6m": 0.15, "volatility_20d": 0.2, "relative_to_market": "KOSPI 대비 양호"}
            }
            ```'''
        return DummyResponse()


def test_get_stock_prices(monkeypatch):
    """주가 데이터 조회 함수 테스트 (DB 모킹)"""
    monkeypatch.setattr(stock_agent_anthropic, "fetch_dicts", lambda sql, params: [
        {"date": "2025-11-19", "close": 70000},
        {"date": "2025-11-18", "close": 69000}
    ])
    result = stock_agent_anthropic.get_stock_prices("005930.KS")
    assert result["ticker"] == "005930.KS"
    assert "current_price" in result


def test_get_financial_metrics(monkeypatch):
    """재무 지표 조회 함수 테스트 (DB 모킹)"""
    monkeypatch.setattr(stock_agent_anthropic, "fetch_dicts", lambda sql, params: [
        {"fiscal_date": "2025-09-30", "freq": "Q", "revenue": 100, "op_income": 10, "net_income": 5}
    ])
    monkeypatch.setattr(stock_agent_anthropic, "fetch_one", lambda sql, params: None)
    result = stock_agent_anthropic.get_financial_metrics("005930.KS")
    assert result["ticker"] == "005930.KS"
    assert "revenue" in result


def test_get_technical_signals(monkeypatch):
    """기술적 지표 조회 함수 테스트 (DB 모킹)"""
    monkeypatch.setattr(stock_agent_anthropic, "fetch_one", lambda sql, params: ["2025-11-19", 70000, 69000, 50, 1, 0.1, 0.2])
    monkeypatch.setattr(stock_agent_anthropic, "fetch_all", lambda sql, params: [[70000, 71000, 69000]])
    result = stock_agent_anthropic.get_technical_signals("005930.KS")
    assert result["ticker"] == "005930.KS"
    assert "trend" in result


import agents.tools

def test_get_news_sentiment(monkeypatch):
    """뉴스 감성 분석 함수 테스트 (모킹)"""
    monkeypatch.setattr(stock_agent_anthropic, "search_stock_news", lambda *args, **kwargs: type("Dummy", (), {"invoke": lambda self, x: {"news": [{"title": "뉴스1", "sentiment_score": 0.5}]}})())
    monkeypatch.setattr(agents.tools, "search_realtime_news_tavily", type("Dummy", (), {"invoke": lambda self, x: {"results": [{"title": "뉴스2", "sentiment_score": 0.2}]}})())
    result = stock_agent_anthropic.get_news_sentiment("005930.KS", "삼성전자")
    assert result["ticker"] == "005930.KS"
    assert "sentiment" in result


def test_run_stock_analysis_agent(monkeypatch):
    """에이전트 전체 실행 테스트 (LLM 모킹)"""
    monkeypatch.setattr(stock_agent_anthropic, "get_chat_model", lambda model_name: DummyLLM)
    result = stock_agent_anthropic.run_stock_analysis_agent("005930.KS", profile="balanced")
    assert "meta" in result
    assert "basic_info" in result
