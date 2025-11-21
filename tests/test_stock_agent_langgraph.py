import pytest
from agents import stock_agent_langgraph

# 더미 LLM 클래스 (모든 분석 노드에서 사용)
class DummyLLM:
    def invoke(self, *args, **kwargs):
        class DummyResponse:
            content = '''```json\n{"market_snapshot": {"current_price": 70000}, "financial_summary": {}, "financial_score": 80, "technical_analysis": {"trend": "uptrend", "rsi14": 60}, "technical_score": 75, "news_and_momentum": {"recent_news_highlights": [{"title": "뉴스", "summary": "요약"}], "sentiment": "positive"}, "news_score": 70, "quality_scores": {"financial_score": 80, "technical_score": 75, "news_score": 70, "overall_score": 75}, "recommendation": {"target_price_range": "77,000 ~ 84,000"}, "scenarios_1y": {"bull_case": {}, "base_case": {}, "bear_case": {}}, "meta": {}, "basic_info": {}}\n```'''
        return DummyResponse()

# 데이터 수집 노드 테스트
@pytest.mark.parametrize("func, key", [
    (stock_agent_langgraph.collect_price_data, "price_data"),
    (stock_agent_langgraph.collect_financial_data, "financial_data"),
    (stock_agent_langgraph.collect_technical_data, "technical_data"),
    (stock_agent_langgraph.collect_news_data, "news_data"),
])
def test_collect_data_nodes(monkeypatch, func, key):
    # DB/뉴스 함수 모킹
    monkeypatch.setattr(stock_agent_langgraph, "get_stock_prices", lambda ticker, days=180: {"ticker": ticker, "data_points": 2})
    monkeypatch.setattr(stock_agent_langgraph, "get_financial_metrics", lambda ticker, quarters=4: {"ticker": ticker, "data_points": 1})
    monkeypatch.setattr(stock_agent_langgraph, "get_technical_signals", lambda ticker: {"ticker": ticker, "trend": "uptrend"})
    monkeypatch.setattr(stock_agent_langgraph, "get_news_sentiment", lambda ticker, company_name: {"ticker": ticker, "news_count": 1})
    state = {"ticker": "005930.KS", "company_name": "삼성전자"}
    result = func(state)
    assert key in result
    assert "error" not in result[key]

# 전문가 분석 노드 테스트
@pytest.mark.parametrize("func, key", [
    (stock_agent_langgraph.financial_analyst, "financial_analysis"),
    (stock_agent_langgraph.technical_analyst, "technical_analysis"),
    (stock_agent_langgraph.news_analyst, "news_analysis"),
])
def test_analyst_nodes(monkeypatch, func, key):
    monkeypatch.setattr(stock_agent_langgraph, "get_chat_model", lambda model_name: DummyLLM())
    state = {
        "ticker": "005930.KS",
        "company_name": "삼성전자",
        "profile": "balanced",
        "model_name": "gpt-4o",
        "price_data": {},
        "financial_data": {},
        "technical_data": {},
        "news_data": {},
        "industry": "반도체",
        "market": "KOSPI",
        "market_cap_level": "대형주"
    }
    result = func(state)
    assert key in result
    assert "error" not in result[key]

# 검증 노드 테스트 (정상/에러 케이스)
def test_validate_financial():
    state = {"financial_analysis": {"market_snapshot": {}, "financial_summary": {}, "financial_score": 80}}
    result = stock_agent_langgraph.validate_financial(state)
    assert result["financial_validation"]["is_valid"]
    # 에러 케이스
    state = {"financial_analysis": {"financial_score": 120}}  # 점수 범위 초과
    result = stock_agent_langgraph.validate_financial(state)
    assert not result["financial_validation"]["is_valid"]

def test_validate_technical():
    state = {"technical_analysis": {"technical_analysis": {"rsi14": 60}, "technical_score": 75}}
    result = stock_agent_langgraph.validate_technical(state)
    assert result["technical_validation"]["is_valid"]
    # 에러 케이스
    state = {"technical_analysis": {"technical_analysis": {"rsi14": 120}, "technical_score": 75}}
    result = stock_agent_langgraph.validate_technical(state)
    assert not result["technical_validation"]["is_valid"]

def test_validate_news():
    state = {"news_analysis": {"news_and_momentum": {"recent_news_highlights": [{"title": "뉴스", "summary": "요약"}], "sentiment": "positive"}, "news_score": 70}}
    result = stock_agent_langgraph.validate_news(state)
    assert result["news_validation"]["is_valid"]
    # 에러 케이스
    state = {"news_analysis": {"news_and_momentum": {"recent_news_highlights": [], "sentiment": "unknown"}, "news_score": 70}}
    result = stock_agent_langgraph.validate_news(state)
    assert not result["news_validation"]["is_valid"]

# 통합 분석 노드 테스트
def test_synthesizer(monkeypatch):
    monkeypatch.setattr(stock_agent_langgraph, "get_chat_model", lambda model_name: DummyLLM())
    state = {
        "ticker": "005930.KS",
        "company_name": "삼성전자",
        "profile": "balanced",
        "model_name": "gpt-4o",
        "market": "KOSPI",
        "industry": "반도체",
        "market_cap_level": "대형주",
        "financial_analysis": {"financial_score": 80},
        "technical_analysis": {"technical_score": 75},
        "news_analysis": {"news_score": 70}
    }
    result = stock_agent_langgraph.synthesizer(state)
    assert "final_report" in result
    assert "error" not in result["final_report"]

# 전체 실행 함수 smoke test
def test_run_langgraph_stock_analysis(monkeypatch):
    monkeypatch.setattr(stock_agent_langgraph, "get_stock_prices", lambda ticker, days=180: {"ticker": ticker, "data_points": 2})
    monkeypatch.setattr(stock_agent_langgraph, "get_financial_metrics", lambda ticker, quarters=4: {"ticker": ticker, "data_points": 1})
    monkeypatch.setattr(stock_agent_langgraph, "get_technical_signals", lambda ticker: {"ticker": ticker, "trend": "uptrend"})
    monkeypatch.setattr(stock_agent_langgraph, "get_news_sentiment", lambda ticker, company_name: {"ticker": ticker, "news_count": 1})
    monkeypatch.setattr(stock_agent_langgraph, "get_chat_model", lambda model_name: DummyLLM())
    monkeypatch.setattr(stock_agent_langgraph, "fetch_one", lambda sql, params: ("005930.KS", "삼성전자", "KOSPI", "SEMI"))
    result = stock_agent_langgraph.run_langgraph_stock_analysis("005930.KS", profile="balanced")
    assert "meta" in result
    assert "basic_info" in result
