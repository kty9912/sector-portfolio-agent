"""
agents/portfolio_agent_anthropic.py

Anthropic Tool Use 방식의 투자 포트폴리오 분석 Agent (v2)
고도화된 입출력 구조: 섹터/종목 선택, 벤치마크 비교, 점수화 등
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timedelta
from decimal import Decimal
import json
import numpy as np

from core.db import fetch_dicts, fetch_one
from core.llm_clients import get_chat_model

from jobs.seed_companies import INDUSTRY_CODE_MAP

from agents.tools import (
    search_sector_news_qdrant,
    search_stock_news,
    search_realtime_news_tavily,
)
from langchain_core.messages import HumanMessage

# =====================================================
# DB에서 동적으로 로드
# =====================================================

def load_available_stocks() -> List[tuple]:
    """DB에서 활성 종목 로드"""
    companies = fetch_dicts("SELECT ticker, name_kr FROM companies WHERE is_active = TRUE ORDER BY ticker")
    return [(c.get("ticker"), c.get("name_kr")) for c in companies]

def load_sector_map() -> Dict[str, str]:
    """DB에서 섹터 맵 로드 (코드 -> 한글)"""
    companies = fetch_dicts("SELECT ticker, industry FROM companies WHERE is_active = TRUE")
    sector_map = {}
    for c in companies:
        ticker = c.get("ticker")
        industry_code = c.get("industry")
        sector_kr = INDUSTRY_CODE_MAP.get(industry_code, industry_code)
        sector_map[ticker] = sector_kr
    return sector_map

def load_sectors() -> List[str]:
    """DB에서 고유 섹터 로드 (한글)"""
    companies = fetch_dicts("SELECT DISTINCT industry FROM companies WHERE is_active = TRUE")
    sectors_set = set()
    for c in companies:
        industry_code = c.get("industry")
        if industry_code:
            sector_kr = INDUSTRY_CODE_MAP.get(industry_code)
            if sector_kr:
                sectors_set.add(sector_kr)
    return sorted(list(sectors_set))

# 초기 로드
AVAILABLE_STOCKS = load_available_stocks()
SECTOR_MAP = load_sector_map()
SECTORS = load_sectors()



# =====================================================
# Tool 정의
# =====================================================

TOOLS = [
    {
        "name": "get_stock_prices",
        "description": "특정 종목의 최근 주가 데이터를 조회합니다. 수익률, 변동성, 벤치마크 대비 성과 등을 계산할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "종목 티커"},
                "days": {"type": "integer", "description": "조회 일수", "default": 250}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_financial_metrics",
        "description": "재무 지표 조회. ROE, 부채비율, 매출성장률 등 재무 점수 계산에 필요한 데이터를 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "quarters": {"type": "integer", "default": 4}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_technical_signals",
        "description": "기술적 지표 조회. RSI, 이동평균, 모멘텀 등 데이터 분석 점수 계산에 사용됩니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_company_info",
        "description": "기업 정보 및 섹터 정보 조회",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "calculate_correlation",
        "description": "종목 간 상관관계 계산. 포트폴리오 분산 효과 평가",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["tickers"]
        }
    },
    {
        "name": "get_stocks_by_sector",
        "description": "특정 섹터의 종목 리스트 조회",
        "input_schema": {
            "type": "object",
            "properties": {
                "sectors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "조회할 섹터 리스트 (예: ['반도체', '바이오'])"
                }
            },
            "required": ["sectors"]
        }
    },
    {
        "name": "calculate_portfolio_performance",
        "description": "포트폴리오 예상 성과 계산. 벤치마크(KOSPI) 대비 수익률, MDD, 샤프비율 등을 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "weights": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "각 종목의 비중 (합이 1이 되어야 함)"
                }
            },
            "required": ["tickers", "weights"]
        }
    }
]


# =====================================================
# Tool 실행 함수들
# =====================================================

def to_float(val) -> float:
    if val is None:
        return 0.0
    return float(val) if isinstance(val, Decimal) else val


def extract_content_text(content) -> str:
    """LLM 응답의 content를 안전하게 문자열로 변환"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # list인 경우 text 타입의 content만 추출하여 결합
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                text_parts.append(item)
        return "".join(text_parts)
    else:
        return str(content)


def get_stock_prices(ticker: str, days: int = 250) -> Dict[str, Any]:
    """주가 데이터 조회"""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    prices = fetch_dicts(
        """SELECT date, close, volume FROM prices_daily
           WHERE ticker = %s AND date >= %s
           ORDER BY date DESC LIMIT %s""",
        (ticker, cutoff_date, days)
    )
    
    if not prices:
        return {"error": f"'{ticker}' 종목의 주가 데이터를 찾을 수 없습니다."}
    
    latest = prices[0]
    oldest = prices[-1] if len(prices) > 1 else latest
    
    # 수익률 계산
    period_return = 0
    if to_float(oldest.get("close")) > 0:
        period_return = (to_float(latest.get("close")) - to_float(oldest.get("close"))) / to_float(oldest.get("close"))
    
    # 변동성 계산
    closes = [to_float(p.get("close", 0)) for p in prices]
    returns = []
    for i in range(1, min(60, len(closes))):
        if closes[i-1] > 0:
            returns.append((closes[i-1] - closes[i]) / closes[i])
    
    volatility = np.std(returns) * np.sqrt(252) if returns else 0
    
    return {
        "ticker": ticker,
        "current_price": to_float(latest.get("close")),
        "period_return_pct": round(period_return * 100, 2),
        "volatility_annual": round(volatility * 100, 2),
        "avg_volume": int(np.mean([to_float(p.get("volume", 0)) for p in prices])),
        "price_data": [
            {"date": str(p.get("date")), "close": to_float(p.get("close"))}
            for p in prices[:60]  # 최근 60일
        ]
    }


def get_financial_metrics(ticker: str, quarters: int = 4) -> Dict[str, Any]:
    """재무 지표 조회"""
    metrics = fetch_dicts(
        """SELECT fiscal_date, roe, opm, debt_ratio, roa, rev_growth_yoy
           FROM fin_metrics WHERE ticker = %s AND freq = 'Q'
           ORDER BY fiscal_date DESC LIMIT %s""",
        (ticker, quarters)
    )
    
    if not metrics:
        return {"error": f"'{ticker}' 종목의 재무 지표를 찾을 수 없습니다."}
    
    latest = metrics[0]
    
    # 재무 점수 계산 (0-100)
    roe = to_float(latest.get("roe", 0)) * 100
    opm = to_float(latest.get("opm", 0)) * 100
    debt_ratio = to_float(latest.get("debt_ratio", 0))
    rev_growth = to_float(latest.get("rev_growth_yoy", 0)) * 100
    
    # 점수화 로직
    roe_score = min(roe / 15 * 100, 100) if roe > 0 else 0
    opm_score = min(opm / 10 * 100, 100) if opm > 0 else 0
    debt_score = max(100 - debt_ratio, 0)
    growth_score = min(max(rev_growth / 20 * 100, 0), 100)
    
    financial_score = (roe_score * 0.3 + opm_score * 0.2 + debt_score * 0.3 + growth_score * 0.2)
    
    return {
        "ticker": ticker,
        "roe": round(roe, 2),
        "opm": round(opm, 2),
        "debt_ratio": round(debt_ratio, 2),
        "revenue_growth_yoy": round(rev_growth, 2),
        "financial_score": round(financial_score, 1)
    }


def get_technical_signals(ticker: str) -> Dict[str, Any]:
    """기술적 지표 조회 - DB의 signals_latest에서 조회"""
    signals = fetch_dicts(
        "SELECT * FROM signals_latest WHERE ticker = %s",
        (ticker,)
    )
    
    if not signals:
        return {"error": f"'{ticker}' 기술적 지표 데이터 없음"}
    
    sig = signals[0]
    
    # RSI 점수화 (30~70 범위가 좋음)
    rsi = to_float(sig.get("rsi14", 50))
    rsi_score = 100 if 30 <= rsi <= 70 else (50 if 20 <= rsi <= 80 else 20)
    
    # 모멘텀 점수화 (양수가 좋음)
    momentum = to_float(sig.get("momentum_20d", 0)) * 100
    momentum_score = min(max((momentum + 10) / 0.2, 0), 100)
    
    # 변동성 (낮을수록 안정적)
    vol = to_float(sig.get("vol_20d", 0))
    vol_score = max(50 - vol * 10, 0)
    
    data_analysis_score = (rsi_score * 0.4 + momentum_score * 0.4 + vol_score * 0.2)
    
    return {
        "ticker": ticker,
        "ma20": round(to_float(sig.get("ma20", 0)), 2),
        "ma60": round(to_float(sig.get("ma60", 0)), 2),
        "rsi14": round(rsi, 2),
        "atr14": round(to_float(sig.get("atr14", 0)), 2),
        "momentum_20d": round(momentum, 2),
        "vol_20d": round(vol, 4),
        "data_analysis_score": round(data_analysis_score, 1),
        "signal": "강세" if data_analysis_score > 60 else ("약세" if data_analysis_score < 40 else "중립")
    }


def get_company_info(ticker: str) -> Dict[str, Any]:
    """기업 정보 조회 - DB에서만 가져오기"""
    companies = fetch_dicts("SELECT ticker, name_kr, industry FROM companies WHERE ticker = %s", (ticker,))
    
    if not companies:
        return {"error": f"'{ticker}' 종목 정보를 찾을 수 없습니다."}
    
    company = companies[0]
    sector_code = company.get("industry")
    sector_kr = INDUSTRY_CODE_MAP.get(sector_code, sector_code)
    
    return {
        "ticker": ticker,
        "name": company.get("name_kr"),
        "sector": sector_kr,
    }


def calculate_correlation(tickers: List[str]) -> Dict[str, Any]:
    """상관관계 계산"""
    if len(tickers) < 2:
        return {"error": "최소 2개 종목 필요"}
    
    returns_matrix = {}
    for ticker in tickers:
        prices = fetch_dicts(
            """SELECT close FROM prices_daily WHERE ticker = %s
               ORDER BY date DESC LIMIT 60""",
            (ticker,)
        )
        if len(prices) < 60:
            continue
        closes = [to_float(p.get("close", 0)) for p in reversed(prices)]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] > 0]
        returns_matrix[ticker] = returns
    
    correlations = {}
    tickers_with_data = list(returns_matrix.keys())
    
    for i, ticker1 in enumerate(tickers_with_data):
        for ticker2 in tickers_with_data[i+1:]:
            if returns_matrix[ticker1] and returns_matrix[ticker2]:
                min_len = min(len(returns_matrix[ticker1]), len(returns_matrix[ticker2]))
                corr = np.corrcoef(
                    returns_matrix[ticker1][:min_len],
                    returns_matrix[ticker2][:min_len]
                )[0, 1]
                correlations[f"{ticker1}_{ticker2}"] = round(float(corr), 3)
    
    avg_corr = np.mean(list(correlations.values())) if correlations else 0
    
    return {
        "average_correlation": round(float(avg_corr), 3),
        "diversification_benefit": "높음" if avg_corr < 0.3 else ("중간" if avg_corr < 0.7 else "낮음")
    }


def get_stocks_by_sector(sectors: List[str]) -> Dict[str, Any]:
    """섹터별 종목 조회"""
    result = {}
    for sector in sectors:
        stocks = [(ticker, name) for ticker, name in AVAILABLE_STOCKS if SECTOR_MAP.get(ticker) == sector]
        result[sector] = [{"ticker": t, "name": n} for t, n in stocks]
    
    return {"sector_stocks": result}


def calculate_portfolio_performance(tickers: List[str], weights: List[float]) -> Dict[str, Any]:
    """포트폴리오 성과 계산"""
    if len(tickers) != len(weights) or abs(sum(weights) - 1.0) > 0.01:
        return {"error": "종목 수와 가중치가 일치하지 않거나 가중치 합이 1이 아닙니다."}
    
    # 각 종목의 수익률과 변동성 가져오기
    stock_metrics = []
    for ticker in tickers:
        prices = fetch_dicts(
            """SELECT close FROM prices_daily WHERE ticker = %s
               ORDER BY date DESC LIMIT 250""",
            (ticker,)
        )
        if not prices:
            continue
        
        closes = [to_float(p.get("close", 0)) for p in reversed(prices)]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] > 0]
        
        annual_return = np.mean(returns) * 252 if returns else 0
        annual_vol = np.std(returns) * np.sqrt(252) if returns else 0
        
        stock_metrics.append({
            "returns": returns,
            "annual_return": annual_return,
            "annual_vol": annual_vol
        })
    
    if not stock_metrics:
        return {"error": "종목 데이터 부족"}
    
    # 포트폴리오 수익률 및 변동성 계산
    portfolio_return = sum(m["annual_return"] * w for m, w in zip(stock_metrics, weights))
    portfolio_vol = np.sqrt(
        sum((m["annual_vol"] ** 2) * (w ** 2) for m, w in zip(stock_metrics, weights))
    )
    
    # 샤프비율 (무위험 이자율 3.5% 가정)
    sharpe_ratio = (portfolio_return - 0.035) / portfolio_vol if portfolio_vol > 0 else 0
    
    # MDD 계산 (간단 추정)
    max_drawdown = -portfolio_vol * 1.5
    
    return {
        "expected_annual_return": round(portfolio_return * 100, 2),
        "annual_volatility": round(portfolio_vol * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "benchmark_alpha": round((portfolio_return - 0.08) * 100, 2)  # KOSPI 8% 가정
    }


# =====================================================
# JSON 검증 함수 (Tool 라우터 직전에 추가)
# =====================================================

def validate_portfolio_json(json_str: str) -> Dict[str, Any]:
    """포트폴리오 JSON 검증 및 기업명 수정"""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"JSON 파싱 실패: {str(e)}", "original": json_str}
    
    # 포트폴리오의 각 항목 검증
    if "portfolio_allocation" in data:
        for item in data["portfolio_allocation"]:
            ticker = item.get("ticker")
            if ticker:
                correct_info = get_company_info(ticker)
                if "error" not in correct_info:
                    # DB의 정확한 이름으로 강제 수정
                    item["name"] = correct_info["name"]
                    item["sector"] = correct_info["sector"]
                    print(f"✓ {ticker}: {correct_info['name']} (검증됨)")
                else:
                    print(f"⚠ {ticker}: 검증 실패 - {correct_info['error']}")
    
    return data

def get_news_analysis_for_portfolio(
    tickers: List[str],
    sectors: List[str],
    risk_profile: str,
    investment_period: str,
    model_name: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """
    LangGraph의 news_agent_node를 Anthropic 에이전트용으로 축약 이식한 버전.
    - 섹터별 뉴스(Qdrant + Tavily) → 섹터 동향 요약
    - 종목별 뉴스(Qdrant + Tavily) → 감성 점수 통합 → news_score(0~100) 계산
    - 최종적으로 news_analysis JSON을 반환
    """
    if not tickers:
        return {
            "analysis_summary": "선택된 종목이 없어 뉴스 분석을 수행하지 못했습니다.",
            "ticker_scores": {},
            "sector_outlook": {},
            "sector_trends": {},
        }

    # ✅ 같은 모델 재사용
    llm = get_chat_model(model_name)

    # 1) 티커별 company_info 선로딩
    company_infos: Dict[str, Dict[str, Any]] = {}
    sectors: List[str] = []

    for t in tickers:
        info = get_company_info(t)
        if "error" in info:
            continue
        company_infos[t] = info
        sector = info.get("sector")
        if sector and sector not in sectors:
            sectors.append(sector)

    # ============================================
    # 1단계: 섹터별 뉴스 수집 + 동향 요약
    # ============================================
    sector_news: Dict[str, Any] = {}
    sector_trends: Dict[str, str] = {}

    for sector in sectors:
        # Qdrant (과거/심층 뉴스)
        qdrant_result = search_sector_news_qdrant.invoke({"sector_name": sector})

        # Tavily (최신 속보)
        tavily_result = search_realtime_news_tavily.invoke({
            "query": f"{sector} 섹터 최신 뉴스 산업 동향",
        })

        sector_news[sector] = {
            "qdrant": qdrant_result,
            "tavily": tavily_result,
        }

        # Tavily 결과 안전하게 처리
        tavily_display = []
        if isinstance(tavily_result, list):
            tavily_display = tavily_result[:5]
        elif isinstance(tavily_result, str):
            tavily_display = [{"content": tavily_result}]
        else:
            tavily_display = [tavily_result] if tavily_result else []

        trend_prompt = f"""
        당신은 '{sector}' 섹터 뉴스 전문가입니다.

        [과거 심층 뉴스 (Qdrant)]
        {json.dumps(qdrant_result.get('news', [])[:8], ensure_ascii=False, indent=2)}

        [최신 속보 (Tavily)]
        {json.dumps(tavily_display, ensure_ascii=False, indent=2)}

        위 두 소스를 종합해, 투자자 관점에서 중요한 **산업 동향**을 3~5문장으로 한국어로 요약해줘.
        - 과거 트렌드 + 최신 이슈 모두 반영
        - 투자 포인트/리스크를 함께 언급
        """
        trend_response = llm.invoke([HumanMessage(content=trend_prompt)])
        sector_trends[sector] = extract_content_text(trend_response.content).strip()

    # ============================================
    # 2단계: 종목별 뉴스 수집 (상위 10개)
    # ============================================
    stock_news: Dict[str, Any] = {}

    for idx, ticker in enumerate(list(company_infos.keys())[:10], 1):
        company_name = company_infos[ticker].get("name")
        # Qdrant (과거 뉴스)
        qdrant_stock = search_stock_news.invoke({
            "ticker": ticker,
            "company_name": company_name,
            "limit": 5,
        })
        # Tavily (최신 속보)
        tavily_stock = search_realtime_news_tavily.invoke({
            "query": f"{company_name} 최신 뉴스",
        })

        # 뉴스 데이터 유효성 검사
        has_tavily_data = isinstance(tavily_stock, list) and len(tavily_stock) > 0
        has_qdrant_data = isinstance(qdrant_stock, dict) and "news" in qdrant_stock and len(qdrant_stock.get("news", [])) > 0

        if has_qdrant_data or has_tavily_data:
            stock_news[ticker] = {
                "qdrant": qdrant_stock,
                "tavily": tavily_stock,
                "company_name": company_name,
            }

    # ============================================
    # 3단계: 종목별 뉴스 점수 계산
    # ============================================
    ticker_scores: Dict[str, Any] = {}

    for ticker, news_data in stock_news.items():
        # Qdrant 뉴스 안전하게 추출
        qdrant_data = news_data.get("qdrant", {})
        qdrant_news = qdrant_data.get("news", []) if isinstance(qdrant_data, dict) else []

        # Tavily 뉴스 안전하게 추출
        tavily_raw = news_data.get("tavily", [])
        tavily_news = []
        if isinstance(tavily_raw, list):
            tavily_news = tavily_raw
        elif isinstance(tavily_raw, str):
            # 문자열인 경우 단일 항목으로 처리
            tavily_news = [{"content": tavily_raw, "title": "검색 요약"}]
        elif isinstance(tavily_raw, dict):
            # 딕셔너리인 경우 리스트로 감싸기
            tavily_news = [tavily_raw]

        company_name = news_data.get("company_name", ticker)

        if not qdrant_news and not tavily_news:
            ticker_scores[ticker] = {
                "news_score": 50,
                "sentiment": "neutral",
                "positive_count": 0,
                "negative_count": 0,
                "qdrant_news_count": 0,
                "tavily_news_count": 0,
                "comment": "뉴스 데이터 부족",
            }
            continue

        # Qdrant 쪽 감성
        qdrant_sentiments = []
        qdrant_scores = []
        for item in qdrant_news:
            if isinstance(item, dict):
                qdrant_sentiments.append(item.get("sentiment", "neutral"))
                qdrant_scores.append(item.get("sentiment_score", 0))

        # Tavily 쪽 감성 (LLM으로 분석)
        tavily_sentiments: List[str] = []
        tavily_scores: List[float] = []

        if tavily_news:
            tavily_prompt = f"""
            다음은 '{company_name}'의 최신 뉴스 목록입니다.

            {json.dumps(tavily_news[:5], ensure_ascii=False, indent=2)}

            각 뉴스의 감성을 분석해서 아래 JSON 형식으로만 답변하세요:

            {{
              "news_sentiments": [
                {{"index": 0, "sentiment": "positive/negative/neutral", "score": 0.8}},
                {{"index": 1, "sentiment": "neutral", "score": 0.0}}
              ]
            }}

            - sentiment: "positive" | "negative" | "neutral" 중 하나
            - score: -1.0 ~ 1.0
            - JSON 이외의 텍스트는 절대 넣지 말 것
            """
            try:
                tavily_sentiment_response = llm.invoke([HumanMessage(content=tavily_prompt)])
                tavily_text = extract_content_text(tavily_sentiment_response.content)

                json_start = tavily_text.find("{")
                json_end = tavily_text.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = tavily_text[json_start:json_end].strip()
                else:
                    json_str = tavily_text.strip()

                tavily_data = json.loads(json_str)
                for item in tavily_data.get("news_sentiments", []):
                    tavily_sentiments.append(item.get("sentiment", "neutral"))
                    tavily_scores.append(item.get("score", 0))
            except Exception:
                tavily_sentiments = ["neutral"] * len(tavily_news)
                tavily_scores = [0] * len(tavily_news)

        all_sentiments = qdrant_sentiments + tavily_sentiments
        all_scores = qdrant_scores + tavily_scores

        if all_scores:
            avg_sentiment_score = sum(all_scores) / len(all_scores)
            news_score = (avg_sentiment_score + 1) * 50  # -1~1 → 0~100
        else:
            news_score = 50

        positive_count = all_sentiments.count("positive")
        negative_count = all_sentiments.count("negative")
        if positive_count > negative_count:
            overall_sentiment = "positive"
        elif negative_count > positive_count:
            overall_sentiment = "negative"
            # 필요시 risk_profile 에 따라 패널티 조정 가능
        else:
            overall_sentiment = "neutral"

        ticker_scores[ticker] = {
            "sentiment": overall_sentiment,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "qdrant_news_count": len(qdrant_news),
            "tavily_news_count": len(tavily_news),
            "comment": f"긍정 {positive_count}건, 부정 {negative_count}건 (Qdrant: {len(qdrant_news)}, Tavily: {len(tavily_news)})",
        }

    # ============================================
    # 4단계: LLM으로 최종 JSON 형태 정리
    # ============================================
    final_prompt = f"""
    당신은 뉴스 및 산업 동향 분석 전문가입니다.

    [투자 조건]
    - 투자 성향: {risk_profile}
    - 투자 기간: {investment_period}

    [섹터별 산업 동향 요약]
    {json.dumps(sector_trends, ensure_ascii=False, indent=2)}

    [종목별 뉴스 점수 (계산값)]
    {json.dumps(ticker_scores, ensure_ascii=False, indent=2)}

    위 데이터를 기반으로 아래 JSON 형식으로만 답변하세요:

    {{
      "analysis_summary": "뉴스 분석 종합 의견 (2~3줄)",
      "ticker_scores": {{
        "005930.KS": {{
          "news_score": 88,
          "sentiment": "positive",
          "comment": "예시 코멘트"
        }}
      }},
      "sector_outlook": {{
        "반도체": "매우 긍정적",
        "바이오": "보통"
      }}
    }}

    - 반드시 JSON 형식만 출력
    - 문자열은 큰따옴표(")만 사용
    """
    final_response = llm.invoke([HumanMessage(content=final_prompt)])
    text = extract_content_text(final_response.content)

    try:
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_str = text[json_start:json_end].strip()
        else:
            json_str = text.strip()

        news_analysis = json.loads(json_str)

        # LLM이 수정한 ticker_scores에 우리가 계산한 값 병합
        if "ticker_scores" in news_analysis:
            for t, calc in ticker_scores.items():
                if t in news_analysis["ticker_scores"]:
                    news_analysis["ticker_scores"][t].update(calc)
                else:
                    news_analysis["ticker_scores"][t] = calc
        else:
            news_analysis["ticker_scores"] = ticker_scores

        if "sector_trends" not in news_analysis:
            news_analysis["sector_trends"] = sector_trends

    except Exception:
        news_analysis = {
            "analysis_summary": f"뉴스 분석 완료. {len(ticker_scores)}개 종목 분석됨.",
            "ticker_scores": ticker_scores,
            "sector_outlook": {},
            "sector_trends": sector_trends,
        }

    return news_analysis


# =====================================================
# Tool 라우터
# =====================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if tool_name == "get_stock_prices":
            return get_stock_prices(**tool_input)
        elif tool_name == "get_financial_metrics":
            return get_financial_metrics(**tool_input)
        elif tool_name == "get_technical_signals":
            return get_technical_signals(**tool_input)
        elif tool_name == "get_company_info":
            return get_company_info(**tool_input)
        elif tool_name == "calculate_correlation":
            return calculate_correlation(**tool_input)
        elif tool_name == "get_stocks_by_sector":
            return get_stocks_by_sector(**tool_input)
        elif tool_name == "calculate_portfolio_performance":
            return calculate_portfolio_performance(**tool_input)
        else:
            return {"error": f"알 수 없는 Tool: {tool_name}"}
    except Exception as e:
        return {"error": f"Tool 실행 오류: {str(e)}"}


# =====================================================
# Agent 실행
# =====================================================

def run_portfolio_agent(
    budget: int,
    investment_targets: Dict[str, List[str]],  # {"sectors": [...], "tickers": [...]}
    risk_profile: str,
    investment_period: str,
    model_name: str = "gpt-4o-mini",
    additional_prompt: str = "",
    max_iterations: int = 20
) -> Dict[str, Any]:
    """
    포트폴리오 분석 Agent (v2)
    
    Args:
        budget: 투자 예산
        investment_targets: {"sectors": ["반도체", "바이오"], "tickers": ["005930.KS", ...]}
        risk_profile: 투자 성향
        investment_period: 투자 기간
        model_name: LLM 모델
        additional_prompt: 사용자 추가 요구사항
        max_iterations: 최대 반복
    """
    
    llm = get_chat_model(model_name)

    # 초기 메시지 수정
    initial_context = "**사전 정보 :**\n\n"
   
    tickers = []
    sectors = []
    # 선택된 모든 종목의 정보를 미리 로드
    if "tickers" in investment_targets:
        initial_context += "선택 종목 정보:\n"
        for ticker in investment_targets["tickers"]:
            company_info = get_company_info(ticker)
            tickers.append(ticker)
            sectors.append(company_info.get("sector", "알수없음"))
            if "error" not in company_info:
                initial_context += f"- {company_info['ticker']}: {company_info['name']} ({company_info['sector']})\n"
    
    if "sectors" in investment_targets:
        sector_stocks = get_stocks_by_sector(investment_targets["sectors"])
        for sector, stocks in sector_stocks.get("sector_stocks", {}).items():
            for stock in stocks:
                tickers.append(stock["ticker"])
                sectors.append(sector)
                initial_context += f"- {stock['ticker']}: {stock['name']} ({sector})\n"

    news_analysis = get_news_analysis_for_portfolio(
        tickers=tickers,
        sectors=sectors,
        risk_profile=risk_profile,
        investment_period=investment_period,
        model_name=model_name,
    )
    
    # 시스템 프롬프트
    system_prompt = f"""당신은 전문 투자 분석가 AI입니다.

**⚠️ 중요: 데이터 무결성 규칙**
- 모든 기업명은 반드시 get_company_info() Tool의 "name" 필드를 사용하세요
- DB에서 제공한 이름을 절대 변경하거나 영문으로 바꾸지 마세요
- 최종 JSON의 모든 "name" 필드는 Tool 결과와 정확히 일치해야 합니다
- 예: "SK하이닉스" → "SK하이닉스" (절대 "SK hynix"로 변경 금지)

**투자 조건:**
- 예산: {budget:,}원
- 투자 대상: {json.dumps(investment_targets, ensure_ascii=False)}
- 투자 성향: {risk_profile}
- 투자 기간: {investment_period}
{f"- 추가 요구사항: {additional_prompt}" if additional_prompt else ""}

**뉴스 분석 사전 데이터 (news_analysis):**
다음 JSON은 Qdrant(과거 뉴스)와 Tavily(최신 속보)를 통합 분석한 결과입니다.
각 종목에 대해 다음 정보가 제공됩니다:
- sentiment: "positive" / "negative" / "neutral"
- positive_count / negative_count: 긍정/부정 기사 개수
- qdrant_news_count / tavily_news_count: 각 소스별 기사 개수
- comment: 한줄 요약 코멘트
- sector_outlook: 섹터별 전망 텍스트 ("매우 긍정적", "긍정적", "중립", "부정적" 등)
- sector_trends: 섹터별 뉴스 트렌드 요약

{json.dumps(news_analysis, ensure_ascii=False, indent=2)}

**뉴스 점수 계산 규칙:**
각 종목의 `scores.news`(0~100)는 위 데이터를 바탕으로 **당신이 직접 판단하여** 다음 기준에 따라 계산합니다.

1. 기본값은 50점입니다.
2. 섹터 전망(sector_outlook)을 반영합니다.
   - "매우 긍정적" 섹터: +15점
   - "긍정적" 섹터: +10점
   - "중립" 섹터: +0점
   - "부정적" 섹터: -10점
   (섹터 정보가 없으면 0점 조정)
3. 종목별 sentiment / 기사 개수를 반영합니다.
   - positive_count > negative_count 인 경우: +5 ~ +15점 범위에서 판단
   - negative_count > positive_count 인 경우: -5 ~ -20점 범위에서 판단
   - 거의 비슷하거나 기사 수가 매우 적으면: -5 ~ +5점 이내로만 조정
4. 투자 성향에 따라 가중치를 조정합니다.
   - 공격적 투자자: 긍정 뉴스가 많은 종목은 조금 더 과감히(최대 +5점 추가)
   - 안정형 투자자: 부정 뉴스가 있는 종목은 보수적으로(최대 -5점 추가)
5. 최종 뉴스 점수는 반드시 0 이상 100 이하가 되도록 합니다.

예시:
- 섹터 전망 "매우 긍정적" + positive_count가 확실히 많은 종목 → 80~90점
- 섹터 전망 "부정적"이고 부정 뉴스가 대부분인 종목 → 20~40점
- 뉴스가 거의 없거나 중립적인 경우 → 45~60점 사이

⚠️ 중요:
- `scores.news`는 위 규칙을 참고하되, 케이스별로 합리적인 범위 내에서 당신이 최종 판단합니다.
- 동일 섹터 내 종목들의 상대적인 분위기도 고려하여, 점수 편차를 적절히 유지하세요.

**분석 절차:**
1. 선택된 섹터/종목의 데이터 수집 (주가, 재무, 기술적 지표)
2. 각 종목별 점수 계산:
   - 데이터 분석 점수 (기술적 지표 기반)
   - 재무 점수 (ROE, 부채비율, 성장률 기반)
   - 뉴스 점수 (news_analysis의 ticker_scores를 우선 사용)
3. 투자 비중 결정 (성향과 기간 고려)
4. 포트폴리오 성과 지표 계산 (수익률, MDD, 샤프비율)
5. 목표가/손절가 제시

**최종 출력 형식 (반드시 ```json 블록 안에 작성):**

```json
{{
  "ai_summary": "  삼성전자(45%), NAVER(30%), 한화오션(25%)으로 구성된 포트폴리오로, IT·조선 등 산업을 고르게 분산해 경기순환 리스크를 완화한 중립형 전략입니다.
  투자 전략은 1년을 기준으로 단계적으로 운영됩니다. 1~3개월 차에는 실적 발표 및 AI 반도체 수요 변화를 모니터링하고, 6개월 시점에는 일정 수익 실현과 함께 NAVER 비중 확대를 검토합니다. 
  12개월 이후에는 경기 회복 국면에 맞춰 삼성전자 중심으로 리밸런싱을 계획하고 있습니다.  종합 평가 결과 82점으로, AI 산업 성장에 따른 장기적 수익성을 노리는 중립형 투자자에게 적합한 포트폴리오로 판단됩니다.",
  "portfolio_allocation": [
    {{
      "ticker": "005930.KS",
      "name": "삼성전자",
      "sector": "반도체",
      "weight": 0.30,
      "amount": 1500000,
      "shares": 21,
      "current_price": 71000,
      "target_price": 85000,
      "stop_loss": 64000,
      "scores": {{
        "data_analysis": 85,
        "financial": 78,
        "news": 82
      }}
    }}
  ],
  "performance_metrics": {{
    "expected_return": 18.5,
    "max_drawdown": -15.2,
    "sharpe_ratio": 1.15,
    "benchmark_alpha": 8.3
  }},
  "chart_data": {{
    "sunburst": [
      {{"name": "반도체", "value": 0.50}},
      {{"name": "삼성전자", "value": 0.30, "parent": "반도체"}},
      {{"name": "SK하이닉스", "value": 0.20, "parent": "반도체"}}
    ],
    "expected_performance": {{
      "months": [1, 3, 6, 12],
      "portfolio": [2.1, 6.5, 11.2, 18.5],
      "benchmark": [1.5, 4.2, 7.8, 12.0]
    }}
  }}
}}
```

모든 Tool을 활용해 정확한 데이터 기반 분석을 수행하세요."""    

    print('initial_context:', initial_context)
    messages = [
        {
            "role": "user",
            "content": f"{system_prompt}\n\n{initial_context}\n\n위 조건으로 포트폴리오를 분석해주세요."
        }
    ]
    
    iteration = 0
    print(f"\n{'='*60}")
    print(f"🤖 포트폴리오 분석 Agent 시작 (모델: {model_name})")
    print(f"{'='*60}\n")
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        
        try:
            llm_with_tools = llm.bind_tools(TOOLS)
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            print(f"❌ LLM 호출 오류: {e}")
            return {
                "success": False,
                "error": f"LLM 호출 실패: {str(e)}",
                "iterations": iteration
            }
        
        # Tool 호출 확인
        has_tool_calls = (
            hasattr(response, 'tool_calls') and 
            response.tool_calls and 
            len(response.tool_calls) > 0
        )
        
        if not has_tool_calls:
            print("\n✅ Agent 분석 완료")
            final_content = extract_content_text(response.content)
            
            # ⭐ JSON 검증 함수 호출
            print("\n🔍 JSON 검증 중...")
            try:
                json_start = final_content.find("```json")
                json_end = final_content.find("```", json_start + 7)
                
                if json_start != -1 and json_end != -1:
                    json_str = final_content[json_start+7:json_end].strip()
                    validated_data = validate_portfolio_json(json_str)
                    
                    if "error" in validated_data:
                        print(f"⚠ 검증 실패: {validated_data['error']}")
                        final_report = final_content
                    else:
                        print("✅ JSON 검증 성공")
                        final_report = final_content[:json_start+7] + json.dumps(
                            validated_data, 
                            ensure_ascii=False, 
                            indent=2
                        ) + final_content[json_end:]
                else:
                    print("⚠ JSON 블록을 찾을 수 없음")
                    final_report = final_content
            except Exception as e:
                print(f"⚠ 검증 중 오류: {str(e)}")
                final_report = final_content
            
            return {
                "success": True,
                "iterations": iteration,
                "final_report": final_report,
                "messages": messages
            }
        
        else:
            print(f"\n🔧 Tool 호출 중...")
            
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls
            })
            
            tool_results = []
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_input = tool_call["args"]
                tool_id = tool_call.get("id", f"call_{iteration}")
                
                print(f"  - {tool_name}({json.dumps(tool_input, ensure_ascii=False)})")
                
                result = execute_tool(tool_name, tool_input)
                
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False)
                })
            
            messages.extend(tool_results)
    
    return {
        "success": False,
        "error": f"최대 반복 횟수({max_iterations}) 초과",
        "iterations": iteration
    }