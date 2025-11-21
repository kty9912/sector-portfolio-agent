"""
agent_test/stock_analyzer_agent.py

단일 종목 분석 에이전트 (Anthropic Tool Use 방식)
포트폴리오 에이전트 구조를 참고한 체계적인 분석 시스템
"""

from __future__ import annotations

# Standard library imports
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Literal

# Third-party library imports
import numpy as np
import yfinance as yf

# Local module imports
from core.db import fetch_dicts, fetch_one, fetch_all
from core.llm_clients import get_chat_model
from agents.tools import search_stock_news

# 산업 코드 매핑 (seed_companies.py와 동일)
INDUSTRY_CODE_MAP = {
    "SEMI": "반도체",
    "BIO": "바이오",
    "DEF": "방산",
    "AI": "AI",
    "NUC": "원자력",
    "UTILSVC": "전력망",
    "SHP": "조선",
}

# =====================================================
# Tool 정의
# =====================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_prices",
            "description": "특정 종목의 최근 주가 데이터를 조회합니다. 수익률, 변동성 계산에 사용됩니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "종목 티커"},
                    "days": {"type": "integer", "description": "조회 일수", "default": 180}
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_metrics",
            "description": "재무 지표 조회. ROE, 부채비율, 매출성장률 등을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "quarters": {"type": "integer", "default": 4}
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_signals",
            "description": "기술적 지표 조회. RSI, 이동평균, 모멘텀 등을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"}
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_sentiment",
            "description": "종목 관련 뉴스 감성 분석 결과를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"}
                },
                "required": ["ticker", "company_name"]
            }
        }
    }
]


# =====================================================
# Tool 구현
# =====================================================

def get_stock_prices(ticker: str, days: int = 180) -> Dict[str, Any]:
    """주가 데이터 조회 (prices_daily 테이블 활용)"""
    try:
        from datetime import datetime, timedelta
        
        # DB에서 최근 데이터 조회
        sql = """
            SELECT date, open, high, low, close, adj_close, volume
            FROM prices_daily
            WHERE ticker = %s
            ORDER BY date DESC
            LIMIT %s
        """
        rows = fetch_dicts(sql, (ticker, days))
        
        if not rows:
            return {"error": "No price data available in DB"}
        
        # 최신순 -> 오래된순으로 정렬
        rows = sorted(rows, key=lambda x: x['date'])
        
        current_price = float(rows[-1]['close'])
        prev_close = float(rows[-2]['close']) if len(rows) > 1 else current_price
        price_change_1d = (current_price - prev_close) / prev_close if prev_close != 0 else 0.0
        
        # 수익률 계산
        returns = {}
        for period, days_back in [("1m", 20), ("3m", 60), ("6m", 120)]:
            if len(rows) > days_back:
                old_price = float(rows[-days_back - 1]['close'])
                returns[period] = (current_price - old_price) / old_price if old_price != 0 else 0.0
        
        # 변동성 계산 (20일)
        if len(rows) >= 20:
            closes = [float(r['close']) for r in rows[-20:]]
            pct_changes = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] != 0]
            volatility = float(np.std(pct_changes) * (252 ** 0.5)) if pct_changes else 0.0
        else:
            volatility = 0.0
        
        return {
            "ticker": ticker,
            "current_price": current_price,
            "price_change_1d": price_change_1d,
            "return_1m": returns.get("1m", 0.0),
            "return_3m": returns.get("3m", 0.0),
            "return_6m": returns.get("6m", 0.0),
            "volatility_20d": volatility,
            "data_points": len(rows)
        }
    except Exception as e:
        return {"error": str(e)}


def get_financial_metrics(ticker: str, quarters: int = 4) -> Dict[str, Any]:
    """재무 지표 조회 (fundamentals + fin_metrics 테이블 활용)"""
    try:
        # fundamentals에서 기본 재무 데이터
        fund_sql = """
            SELECT fiscal_date, freq, revenue, op_income, net_income, 
                   total_assets, total_liab, equity, ebitda, 
                   cash_from_ops, capex
            FROM fundamentals
            WHERE ticker = %s
            ORDER BY fiscal_date DESC, freq DESC
            LIMIT %s
        """
        fund_rows = fetch_dicts(fund_sql, (ticker, quarters))
        
        if not fund_rows:
            return {"error": "No fundamental data available"}
        
        # fin_metrics에서 계산된 지표
        metrics_sql = """
            SELECT fiscal_date, freq, roe, opm, debt_ratio, 
                   roa, rev_growth_yoy, fcf
            FROM fin_metrics
            WHERE ticker = %s
            ORDER BY fiscal_date DESC, freq DESC
            LIMIT %s
        """
        metrics_rows = fetch_dicts(metrics_sql, (ticker, quarters))
        
        # 최신 데이터
        latest_fund = fund_rows[0]
        latest_metrics = metrics_rows[0] if metrics_rows else {}
        
        return {
            "ticker": ticker,
            "latest_period": str(latest_fund['fiscal_date']),
            "freq": latest_fund['freq'],
            "revenue": float(latest_fund['revenue'] or 0),
            "op_income": float(latest_fund['op_income'] or 0),
            "net_income": float(latest_fund['net_income'] or 0),
            "ebitda": float(latest_fund.get('ebitda') or 0),
            "total_assets": float(latest_fund.get('total_assets') or 0),
            "total_liab": float(latest_fund.get('total_liab') or 0),
            "equity": float(latest_fund.get('equity') or 0),
            "opm": float(latest_metrics.get('opm') or 0),
            "roe": float(latest_metrics.get('roe') or 0),
            "roa": float(latest_metrics.get('roa') or 0),
            "debt_ratio": float(latest_metrics.get('debt_ratio') or 0),
            "rev_growth_yoy": float(latest_metrics.get('rev_growth_yoy') or 0),
            "fcf": float(latest_metrics.get('fcf') or 0),
            "history": [
                {
                    "period": str(r['fiscal_date']),
                    "freq": r['freq'],
                    "revenue": float(r['revenue'] or 0),
                    "op_income": float(r['op_income'] or 0)
                }
                for r in fund_rows
            ],
            "data_points": len(fund_rows)
        }
    except Exception as e:
        return {"error": str(e)}


def get_technical_signals(ticker: str) -> Dict[str, Any]:
    """기술적 지표 조회 (signals_latest 테이블 활용)"""
    try:
        # signals_latest에서 계산된 지표 조회
        signals_sql = """
            SELECT asof, ma20, ma60, rsi14, atr14, momentum_20d, vol_20d
            FROM signals_latest
            WHERE ticker = %s
        """
        signal = fetch_one(signals_sql, (ticker,))
        
        if not signal:
            return {"error": "No technical signals available"}
        
        # prices_daily에서 현재가와 고저가 조회
        price_sql = """
            SELECT close, high, low
            FROM prices_daily
            WHERE ticker = %s
            ORDER BY date DESC
            LIMIT 60
        """
        price_rows = fetch_all(price_sql, (ticker,))
        
        if not price_rows:
            return {"error": "No price data available"}
        
        current_price = float(price_rows[0][0])
        ma20 = float(signal[1]) if signal[1] else current_price
        ma60 = float(signal[2]) if signal[2] else current_price
        
        # 추세 판단
        if current_price > ma20 > ma60:
            trend = "uptrend"
        elif current_price < ma20 < ma60:
            trend = "downtrend"
        else:
            trend = "sideways"
        
        # 변동성 레벨
        vol_20d = float(signal[6]) if signal[6] else 0.0
        if vol_20d < current_price * 0.015:
            vol_level = "low"
        elif vol_20d < current_price * 0.03:
            vol_level = "medium"
        else:
            vol_level = "high"
        
        # 지지/저항 구간 (최근 60일 고저가 기준)
        lows = [float(r[2]) for r in price_rows if r[2]]
        highs = [float(r[1]) for r in price_rows if r[1]]
        
        min_low = min(lows) if lows else current_price * 0.9
        max_high = max(highs) if highs else current_price * 1.1
        
        return {
            "ticker": ticker,
            "asof": str(signal[0]),
            "rsi14": float(signal[3]) if signal[3] else 50.0,
            "ma20": ma20,
            "ma60": ma60,
            "atr14": float(signal[4]) if signal[4] else 0.0,
            "momentum_20d": float(signal[5]) if signal[5] else 0.0,
            "vol_20d": vol_20d,
            "trend": trend,
            "volatility_20d_level": vol_level,
            "support_zone": f"{int(min_low * 0.98):,} ~ {int(min_low * 1.02):,}",
            "resistance_zone": f"{int(max_high * 0.98):,} ~ {int(max_high * 1.02):,}",
            "ma_position": "above_ma20_ma60" if current_price > ma20 > ma60 else "below_ma20_ma60" if current_price < ma20 < ma60 else "mixed"
        }
    except Exception as e:
        return {"error": str(e)}


def get_news_sentiment(ticker: str, company_name: str) -> Dict[str, Any]:
    """뉴스 감성 분석 (실제 데이터)"""
    try:
        from agents.tools import search_realtime_news_tavily, search_stock_news

        # Tavily를 사용하여 실시간 뉴스 검색
        tavily_raw = search_realtime_news_tavily.invoke({"query": company_name})

        # Tavily 결과 타입 처리
        if isinstance(tavily_raw, list):
            tavily_news = tavily_raw
        elif isinstance(tavily_raw, dict):
            tavily_news = tavily_raw.get('results', [])
        elif isinstance(tavily_raw, str):
            tavily_news = []
        else:
            tavily_news = []

        # Qdrant 뉴스 검색
        qdrant_result = search_stock_news.invoke({"ticker": ticker, "company_name": company_name})
        qdrant_news = qdrant_result.get('news', []) if isinstance(qdrant_result, dict) else []
        
        all_news = tavily_news + qdrant_news
        news_list = []

        for news in all_news:
            if not isinstance(news, dict):
                continue

            title = news.get('title', news.get('content', '제목 없음'))
            sentiment_score = news.get('sentiment_score', news.get('score', 0))

            news_list.append({
                "title": title,
                "sentiment_score": sentiment_score,
            })

        # 뉴스가 없는 경우 기본값 반환
        if not news_list:
            return {
                "ticker": ticker,
                "company_name": company_name,
                "news_count": 0,
                "sentiment": "neutral",
                "avg_sentiment_score": 0,
                "articles": [],
                "highlights": []
            }

        # 평균 감성 점수
        avg_score = sum(n['sentiment_score'] for n in news_list) / len(news_list)
        
        if avg_score > 0.2:
            sentiment = "positive"
        elif avg_score < -0.2:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        highlights = [
            {
                "title": n['title'],
                "summary": f"{company_name}의 최근 동향에 대한 분석입니다. 시장 전문가들은 {'긍정적인' if n['sentiment_score'] > 0 else '부정적인' if n['sentiment_score'] < 0 else '중립적인'} 의견을 제시하고 있습니다."
            }
            for n in news_list[:3]
        ]
        
        return {
            "ticker": ticker,
            "company_name": company_name,
            "news_count": len(news_list),
            "sentiment": sentiment,
            "avg_sentiment_score": round(avg_score, 3),
            "articles": news_list,
            "highlights": highlights
        }
    except Exception as e:
        return {"error": str(e)}



# =====================================================
# Tool 실행 라우터
# =====================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Tool 실행"""
    if tool_name == "get_stock_prices":
        return get_stock_prices(**tool_input)
    elif tool_name == "get_financial_metrics":
        return get_financial_metrics(**tool_input)
    elif tool_name == "get_technical_signals":
        return get_technical_signals(**tool_input)
    elif tool_name == "get_news_sentiment":
        return get_news_sentiment(**tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


# =====================================================
# Agent 실행
# =====================================================

def run_stock_analysis_agent(
    ticker: str,
    profile: Literal["aggressive", "balanced", "conservative"] = "balanced",
    model_name: str = "gpt-4o"
) -> Dict[str, Any]:
    """
    단일 종목 분석 에이전트 실행
    
    Args:
        ticker: 종목 코드 (예: "005930.KS")
        profile: 투자 성향
        model_name: 사용할 LLM 모델
    
    Returns:
        분석 결과 JSON
    """
    
    print(f"\n{'='*60}")
    print(f"🔍 단일 종목 분석 시작: {ticker}")
    print(f"{'='*60}\n")
    
    # 기본 정보 조회
    market_cap_level = "중형주"
    company_name = "Unknown"
    market = "KOSPI"
    industry = "기타"
    
    try:
        sql = "SELECT ticker, name_kr, market, industry FROM companies WHERE ticker = %s"
        company = fetch_one(sql, (ticker,))
        
        if company:
            company_name = company[1] or ticker
            market = company[2] or "KOSPI"
            industry_code = company[3]
            # 산업 코드를 한글로 변환
            industry = INDUSTRY_CODE_MAP.get(industry_code, industry_code or "기타")
            
            # 시가총액 조회 (yfinance)
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
            # 시가총액 레벨 분류 (한글)
            if market_cap > 10_000_000_000_000:  # 10조원 이상
                market_cap_level = "대형주"
            elif market_cap > 1_000_000_000_000:  # 1조원 이상
                market_cap_level = "중형주"
            else:
                market_cap_level = "소형주"
            
            print(f"📊 종목 정보: {company_name} ({ticker})")
            print(f"   시장: {market} | 업종: {industry} | 시가총액: {market_cap_level}")
        else:
            # yfinance로 fallback
            print(f"⚠️ DB에 {ticker} 정보 없음 - yfinance 사용")
            stock = yf.Ticker(ticker)
            info = stock.info
            company_name = info.get('longName', ticker)
            market = "KOSPI" if ".KS" in ticker else "KOSDAQ" if ".KQ" in ticker else "해외"
            industry = info.get('industry', '기타')
            market_cap = info.get('marketCap', 0)
            
            if market_cap > 10_000_000_000_000:
                market_cap_level = "대형주"
            elif market_cap > 1_000_000_000_000:
                market_cap_level = "중형주"
            else:
                market_cap_level = "소형주"
    except Exception as e:
        print(f"❌ 기본 정보 조회 오류: {e}")
        # 기본값 유지 (이미 선언됨)
    
    # LLM 모델 초기화
    llm = get_chat_model(model_name)
    
    # 시스템 프롬프트
    system_prompt = f"""당신은 전문 금융 애널리스트입니다.
주어진 종목({company_name}, {ticker})에 대해 종합적인 투자 분석을 수행하고,
**반드시 ```json 코드 블록 안에** 완전한 JSON 형식으로 결과를 반환하세요.

투자 성향: {profile}
- aggressive: 높은 수익률 추구, 리스크 감수
- balanced: 균형잡힌 접근
- conservative: 안정성 우선, 리스크 최소화

**중요: 응답은 반드시 다음과 같이 시작해야 합니다:**
```json
{{
  "meta": {{ ... }},
  ...
}}
```

**출력 형식 (JSON):**

{{
  "meta": {{
    "generated_at": "2025-11-14T14:30:00+09:00",
    "ticker": "{ticker}",
    "data_asof": "2025-11-13",
    "profile": "{profile}"
  }},
  "basic_info": {{
    "ticker": "{ticker}",
    "name_kr": "{company_name}",
    "market": "{market}",
    "industry": "{industry}",
    "market_cap_level": "{market_cap_level}",
    "summary_sentence": "종목 요약 (1-2문장)"
  }},
  "market_snapshot": {{
    "current_price": 78000,
    "price_change_1d": -0.012,
    "return_1m": 0.061,
    "return_3m": 0.125,
    "return_6m": 0.182,
    "volatility_20d": 0.17,
    "relative_to_market": "KOSPI 대비 설명"
  }},
  "financial_summary": {{
    "latest_period": "2025-09-30",
    "freq": "Q",
    "revenue": 85000000000000,
    "op_income": 15300000000000,
    "net_income": 10900000000000,
    "yoy_revenue_growth": 0.12,
    "yoy_op_income_growth": 0.28,
    "opm": 0.18,
    "roe": 0.14,
    "roa": 0.09,
    "debt_ratio": 0.45,
    "fcf": 3500000000000,
    "financial_comment": "재무 상태 분석 코멘트"
  }},
  "quality_scores": {{
    "financial_score": 82,
    "technical_score": 74,
    "news_score": 68,
    "overall_score": 75,
    "score_comment": "점수에 대한 종합 설명"
  }},
  "technical_analysis": {{
    "trend": "uptrend/downtrend/sideways",
    "rsi14": 62.3,
    "ma_position": "above_ma20_ma60",
    "momentum_20d": 0.083,
    "volatility_20d_level": "low/medium/high",
    "support_resistance": {{
      "support_zone": "74,000 ~ 75,000",
      "resistance_zone": "82,000 ~ 85,000"
    }},
    "technical_comment": "기술적 분석 코멘트"
  }},
  "news_and_momentum": {{
    "recent_news_highlights": [
      {{"title": "뉴스 제목", "summary": "뉴스 요약"}}
    ],
    "sentiment": "positive/neutral/negative",
    "sector_trend": "업종 트렌드 설명",
    "news_comment": "{company_name} 관련 뉴스 분석 코멘트 (종목명 사용)"
  }},
  "scenarios_1y": {{
    "bull_case": {{
      "description": "강세 시나리오 설명",
      "expected_return_range": "15% ~ 35%"
    }},
    "base_case": {{
      "description": "기본 시나리오 설명",
      "expected_return_range": "5% ~ 15%"
    }},
    "bear_case": {{
      "description": "약세 시나리오 설명",
      "expected_return_range": "-10% ~ 0%"
    }},
    "scenario_comment": "시나리오 분석 코멘트"
  }},
  "risks": {{
    "major_risks": [
      {{
        "title": "리스크 제목",
        "description": "리스크 설명",
        "severity": "high/medium/low"
      }}
    ]
  }},
  "investment_thesis": {{
    "key_points": [
      "핵심 투자 포인트 1",
      "핵심 투자 포인트 2",
      "핵심 투자 포인트 3"
    ],
    "long_form_summary": "{company_name}에 대한 종합 투자 의견 (종목명 포함하여 3-5문장)"
  }},
  "recommendation": {{
    "rating": "BUY/HOLD/SELL",
    "time_horizon_months": 12,
    "confidence_level": "high/medium/low",
    "target_price_range": "88,000 ~ 92,000",
    "stop_loss_hint": "70,000 근처 이탈 시 주의",
    "recommendation_comment": "투자 추천 코멘트"
  }},
  "appendix_data": {{
    "indicator_snapshot": {{
      "ma20": 77500,
      "ma60": 74820,
      "rsi14": 62.3
    }}
  }}
}}

**중요 지침:**
1. 반드시 Tool을 사용하여 실제 데이터를 조회하세요
2. 최종 응답은 반드시 ```json 코드 블록으로 감싸야 합니다
3. JSON 형식이 완벽하게 유효해야 합니다 (콤마, 따옴표 등)
4. 모든 숫자는 숫자 타입으로, 문자열은 따옴표로 감싸세요
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""티커 {ticker} ({company_name})를 {profile} 성향으로 분석해주세요.

**중요: 반드시 다음 단계를 따르세요:**
1. 먼저 Tool을 사용하여 데이터를 수집하세요 (get_stock_prices, get_financial_metrics, get_technical_signals, get_news_sentiment)
2. 수집한 데이터를 바탕으로 분석을 수행하세요
3. 최종 응답은 반드시 ```json 코드 블록으로 시작하는 완전한 JSON을 반환하세요

예시 형식:
```json
{{
  "meta": {{"generated_at": "2025-11-14T10:00:00", ...}},
  "basic_info": {{...}},
  ...
}}
```

절대 마크다운이나 일반 텍스트로 응답하지 마세요. 오직 JSON만 반환하세요."""}
    ]
    
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        
        try:
            response = llm.invoke(
                messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            # Tool 사용이 필요한 경우
            if hasattr(response, 'tool_calls') and response.tool_calls:
                messages.append(response)
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get('name') or tool_call.get('function', {}).get('name')
                    tool_input = tool_call.get('args') or tool_call.get('function', {}).get('arguments', {})
                    tool_id = tool_call.get('id')
                    
                    # arguments가 문자열일 경우 파싱
                    if isinstance(tool_input, str):
                        tool_input = json.loads(tool_input)
                    
                    print(f"  🔧 Tool 실행: {tool_name}({tool_input})")
                    
                    tool_result = execute_tool(tool_name, tool_input)
                    
                    # 결과 데이터 확인
                    if isinstance(tool_result, dict):
                        if 'error' in tool_result:
                            print(f"     ⚠️ 에러: {tool_result.get('error')}")
                        else:
                            # 데이터 포인트 개수 출력
                            data_size = sum(1 for v in tool_result.values() if v is not None)
                            print(f"     ✓ 데이터 {data_size}개 필드 수집됨")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })
                
                # 모든 Tool 실행 후, JSON 생성 요청 추가
                if iteration == 1:  # 첫 iteration에서 모든 Tool 실행 후
                    messages.append({
                        "role": "user",
                        "content": """이제 수집한 모든 데이터를 바탕으로 최종 JSON 분석 보고서를 작성하세요.

**반드시 아래 형식을 따르세요:**

```json
{
  "meta": {...},
  "basic_info": {...},
  "market_snapshot": {...},
  "financial_summary": {...},
  "quality_scores": {...},
  "technical_analysis": {...},
  "news_and_momentum": {...},
  "scenarios_1y": {...},
  "risks": {...},
  "investment_thesis": {...},
  "recommendation": {...},
  "appendix_data": {...}
}
```

다른 텍스트 없이 오직 JSON만 반환하세요."""
                    })
                
                continue
            
            # 최종 응답
            final_content = response.content
            
            print(f"\n✅ 분석 완료 (반복: {iteration}회)")
            print(f"📝 응답 길이: {len(final_content)} 문자")
            
            # JSON 파싱 시도
            try:
                import re
                
                # 1. ```json 블록 찾기
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', final_content, re.IGNORECASE)
                if json_match:
                    json_str = json_match.group(1).strip()
                    print("✓ ```json 블록 발견")
                else:
                    # 2. { } 로 감싸진 JSON 찾기
                    json_match = re.search(r'\{[\s\S]*\}', final_content)
                    if json_match:
                        json_str = json_match.group(0).strip()
                        print("✓ JSON 객체 발견 (블록 없음)")
                    else:
                        json_str = final_content
                        print("⚠️ JSON 형식 발견 안됨")
                
                result_data = json.loads(json_str)
                print("✓ JSON 파싱 성공")
                
                # 목표가 검증 및 수정
                try:
                    current_price = result_data.get('market_snapshot', {}).get('current_price', 0)
                    target_range = result_data.get('recommendation', {}).get('target_price_range', '')
                    
                    if current_price > 0 and target_range:
                        # "88,000 ~ 92,000" 형식에서 숫자 추출
                        import re
                        numbers = re.findall(r'[\d,]+', target_range)
                        if len(numbers) >= 2:
                            target_low = int(numbers[0].replace(',', ''))
                            target_high = int(numbers[1].replace(',', ''))
                            
                            # 목표가가 현재가보다 낮은 경우 수정
                            if target_high < current_price:
                                print(f"⚠️ 목표가 수정: {target_range} → 현재가 기준으로 조정")
                                # 현재가의 10~20% 상승으로 재설정
                                new_low = int(current_price * 1.10)
                                new_high = int(current_price * 1.20)
                                result_data['recommendation']['target_price_range'] = f"{new_low:,} ~ {new_high:,}"
                                print(f"   수정된 목표가: {result_data['recommendation']['target_price_range']}")
                except Exception as e:
                    print(f"⚠️ 목표가 검증 중 오류: {e}")
                
                return result_data
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 파싱 실패: {e}")
                print(f"파싱 시도한 문자열 (처음 200자): {json_str[:200]}")
                # JSON 파싱 실패 시 텍스트 그대로 반환
                return {
                    "raw_response": final_content,
                    "parse_error": str(e),
                    "meta": {
                        "generated_at": datetime.now().isoformat(),
                        "ticker": ticker,
                        "profile": profile
                    }
                }
        
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            return {
                "error": str(e),
                "meta": {
                    "generated_at": datetime.now().isoformat(),
                    "ticker": ticker,
                    "profile": profile
                }
            }
    
    print(f"⚠️ 최대 반복 횟수 도달")
    return {
        "error": "Max iterations reached",
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "ticker": ticker,
            "profile": profile
        }
    }


# =====================================================
# CLI 테스트
# =====================================================

if __name__ == "__main__":
    import sys
    
    ticker = sys.argv[1] if len(sys.argv) > 1 else "005930.KS"
    profile = sys.argv[2] if len(sys.argv) > 2 else "balanced"
    
    result = run_stock_analysis_agent(ticker=ticker, profile=profile)
    
    print("\n" + "="*60)
    print("📊 분석 결과")
    print("="*60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
