import pytest
from agents.portfolio_agent_anthropic import (
    load_available_stocks, load_sector_map, load_sectors, get_available_stocks, get_sector_map, get_sectors,
    get_stock_prices, get_financial_metrics, get_technical_signals, get_company_info,
    validate_portfolio_json, execute_tool
)

# 1. DB/데이터 로드 함수 테스트
def test_load_available_stocks(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = get_available_stocks()
    assert isinstance(stocks, list)
    assert len(stocks) > 0

def test_load_sector_map(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql: [{"ticker": "005930.KS", "industry": "반도체"}])
    sector_map = get_sector_map()
    assert isinstance(sector_map, dict)
    assert len(sector_map) > 0

def test_load_sectors(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql, params=None: [{"industry": "SEMI"}])
    sectors = get_sectors()
    assert isinstance(sectors, list)
    assert len(sectors) > 0

# 2. 주요 Tool 함수 테스트 (조회만)
def test_get_stock_prices(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_anthropic.get_stock_prices", lambda ticker: {"ticker": ticker, "current_price": 70000})
    result = get_stock_prices(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_financial_metrics(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_anthropic.get_financial_metrics", lambda ticker: {"ticker": ticker, "roe": 10})
    result = get_financial_metrics(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_technical_signals(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_anthropic.get_technical_signals", lambda ticker: {"ticker": ticker, "rsi": 50})
    result = get_technical_signals(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_company_info(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_anthropic.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_anthropic.get_company_info", lambda ticker: {"ticker": ticker, "name_kr": "삼성전자"})
    result = get_company_info(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

# 3. JSON 검증 함수 테스트
def test_validate_portfolio_json_valid():
    json_str = '{"portfolio_allocation": [{"ticker": "005930.KS", "name": "삼성전자", "sector": "반도체"}]}'
    result = validate_portfolio_json(json_str)
    assert isinstance(result, dict)
    assert "portfolio_allocation" in result

def test_validate_portfolio_json_invalid():
    json_str = '{"portfolio_allocation": [INVALID_JSON}'
    result = validate_portfolio_json(json_str)
    assert "error" in result

# 4. 뉴스 분석 함수 테스트 (smoke)
def test_get_news_analysis_for_portfolio_smoke():
    stocks = load_available_stocks()
    tickers = [stocks[0][0]]
    sectors = [load_sector_map()[tickers[0]]] if tickers else []
    from agents import portfolio_agent_anthropic

    # LLM mock: get_chat_model을 항상 mock 객체 반환하도록
    def mock_get_chat_model(model_name):
        class DummyLLM:
            def invoke(self, *args, **kwargs):
                class DummyResponse:
                    content = "요약"
                return DummyResponse()
        return DummyLLM()

    original_get_chat_model = portfolio_agent_anthropic.get_chat_model
    portfolio_agent_anthropic.get_chat_model = mock_get_chat_model

    try:
        result = portfolio_agent_anthropic.get_news_analysis_for_portfolio(
            tickers=tickers,
            sectors=sectors,
            risk_profile="중립",
            investment_period="단기",
            model_name='gpt-4o'
        )
        assert isinstance(result, dict)
        assert "analysis_summary" in result
    finally:
        portfolio_agent_anthropic.get_chat_model = original_get_chat_model

# 5. Tool 라우터 테스트
def test_execute_tool_get_stock_prices():
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    result = execute_tool("get_stock_prices", {"ticker": ticker})
    assert isinstance(result, dict)
    assert "ticker" in result

def test_execute_tool_unknown():
    result = execute_tool("unknown_tool", {})
    assert "error" in result
