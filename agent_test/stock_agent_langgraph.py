"""
agent_test/stock_agent_langgraph.py

LangGraph 기반 멀티 에이전트 단일 종목 분석 시스템
- 재무 분석 전문가 (Financial Analyst)
- 기술적 분석 전문가 (Technical Analyst)
- 뉴스 분석 전문가 (News Analyst)
- 통합 분석가 (Synthesizer)
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Dict, Any, List, TypedDict, Literal, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from core.db import fetch_dicts, fetch_one, fetch_all
from core.llm_clients import get_chat_model
from agents.tools import search_stock_news
import numpy as np

# 기존 Tool 함수들 import
from agent_test.stock_agent_anthropic import (
    get_stock_prices,
    get_financial_metrics,
    get_technical_signals,
    get_news_sentiment,
    INDUSTRY_CODE_MAP
)

# =====================================================
# State 정의
# =====================================================

class AnalysisState(TypedDict):
    """분석 상태를 관리하는 State"""
    # 입력
    ticker: str
    company_name: str
    market: str
    industry: str
    market_cap_level: str
    profile: Literal["aggressive", "balanced", "conservative"]
    
    # 수집된 데이터
    price_data: Dict[str, Any]
    financial_data: Dict[str, Any]
    technical_data: Dict[str, Any]
    news_data: Dict[str, Any]
    
    # 각 전문가의 분석 결과
    financial_analysis: Dict[str, Any]
    technical_analysis: Dict[str, Any]
    news_analysis: Dict[str, Any]
    
    # 최종 결과
    final_report: Dict[str, Any]
    
    # 메타
    messages: Annotated[List, operator.add]
    errors: Annotated[List[str], operator.add]


# =====================================================
# 데이터 수집 노드 (병렬 실행)
# =====================================================

def collect_price_data(state: AnalysisState) -> Dict[str, Any]:
    """주가 데이터 수집"""
    print("💰 [Price Collector] 주가 데이터 수집 중...")
    ticker = state["ticker"]
    
    try:
        data = get_stock_prices(ticker, days=180)
        print(f"   ✓ 주가 데이터 수집 완료: {data.get('data_points', 0)}개 포인트")
        return {"price_data": data}
    except Exception as e:
        print(f"   ❌ 주가 데이터 수집 실패: {e}")
        return {"price_data": {"error": str(e)}, "errors": [f"price_data: {str(e)}"]}


def collect_financial_data(state: AnalysisState) -> Dict[str, Any]:
    """재무 데이터 수집"""
    print("📊 [Financial Collector] 재무 데이터 수집 중...")
    ticker = state["ticker"]
    
    try:
        data = get_financial_metrics(ticker, quarters=4)
        print(f"   ✓ 재무 데이터 수집 완료: {data.get('data_points', 0)}개 분기")
        return {"financial_data": data}
    except Exception as e:
        print(f"   ❌ 재무 데이터 수집 실패: {e}")
        return {"financial_data": {"error": str(e)}, "errors": [f"financial_data: {str(e)}"]}


def collect_technical_data(state: AnalysisState) -> Dict[str, Any]:
    """기술적 지표 수집"""
    print("📈 [Technical Collector] 기술적 지표 수집 중...")
    ticker = state["ticker"]
    
    try:
        data = get_technical_signals(ticker)
        print(f"   ✓ 기술적 지표 수집 완료")
        return {"technical_data": data}
    except Exception as e:
        print(f"   ❌ 기술적 지표 수집 실패: {e}")
        return {"technical_data": {"error": str(e)}, "errors": [f"technical_data: {str(e)}"]}


def collect_news_data(state: AnalysisState) -> Dict[str, Any]:
    """뉴스 데이터 수집"""
    print("📰 [News Collector] 뉴스 데이터 수집 중...")
    ticker = state["ticker"]
    company_name = state["company_name"]
    
    try:
        data = get_news_sentiment(ticker, company_name)
        print(f"   ✓ 뉴스 데이터 수집 완료: {data.get('news_count', 0)}개 기사")
        return {"news_data": data}
    except Exception as e:
        print(f"   ❌ 뉴스 데이터 수집 실패: {e}")
        return {"news_data": {"error": str(e)}, "errors": [f"news_data: {str(e)}"]}


# =====================================================
# 전문가 분석 노드 (병렬 실행)
# =====================================================

def financial_analyst(state: AnalysisState) -> Dict[str, Any]:
    """재무 분석 전문가"""
    print("\n🏦 [Financial Analyst] 재무 분석 시작...")
    
    llm = get_chat_model("gpt-4o")
    
    prompt = f"""당신은 재무 분석 전문가입니다.
종목: {state['company_name']} ({state['ticker']})
투자 성향: {state['profile']}

다음 데이터를 바탕으로 재무 분석을 수행하세요:

**주가 데이터:**
{json.dumps(state.get('price_data', {}), ensure_ascii=False, indent=2)}

**재무 데이터:**
{json.dumps(state.get('financial_data', {}), ensure_ascii=False, indent=2)}

**출력 형식 (JSON):**
```json
{{
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
  "financial_score": 82
}}
```

반드시 ```json 블록으로 감싸서 반환하세요."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        
        # JSON 추출
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
        if json_match:
            result = json.loads(json_match.group(1).strip())
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            result = json.loads(json_match.group(0).strip()) if json_match else {}
        
        print(f"   ✓ 재무 분석 완료 (점수: {result.get('financial_score', 'N/A')})")
        return {"financial_analysis": result}
    
    except Exception as e:
        print(f"   ❌ 재무 분석 실패: {e}")
        return {"financial_analysis": {"error": str(e)}, "errors": [f"financial_analysis: {str(e)}"]}


def technical_analyst(state: AnalysisState) -> Dict[str, Any]:
    """기술적 분석 전문가"""
    print("\n📉 [Technical Analyst] 기술적 분석 시작...")
    
    llm = get_chat_model("gpt-4o")
    
    prompt = f"""당신은 기술적 분석 전문가입니다.
종목: {state['company_name']} ({state['ticker']})
투자 성향: {state['profile']}

다음 데이터를 바탕으로 기술적 분석을 수행하세요:

**기술적 지표:**
{json.dumps(state.get('technical_data', {}), ensure_ascii=False, indent=2)}

**주가 데이터:**
{json.dumps(state.get('price_data', {}), ensure_ascii=False, indent=2)}

**출력 형식 (JSON):**
```json
{{
  "technical_analysis": {{
    "trend": "uptrend",
    "rsi14": 62.3,
    "ma_position": "above_ma20_ma60",
    "momentum_20d": 0.083,
    "volatility_20d_level": "medium",
    "support_resistance": {{
      "support_zone": "74,000 ~ 75,000",
      "resistance_zone": "82,000 ~ 85,000"
    }},
    "technical_comment": "기술적 분석 코멘트"
  }},
  "technical_score": 74,
  "appendix_data": {{
    "indicator_snapshot": {{
      "ma20": 77500,
      "ma60": 74820,
      "rsi14": 62.3
    }}
  }}
}}
```

반드시 ```json 블록으로 감싸서 반환하세요."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        
        # JSON 추출
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
        if json_match:
            result = json.loads(json_match.group(1).strip())
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            result = json.loads(json_match.group(0).strip()) if json_match else {}
        
        print(f"   ✓ 기술적 분석 완료 (점수: {result.get('technical_score', 'N/A')})")
        return {"technical_analysis": result}
    
    except Exception as e:
        print(f"   ❌ 기술적 분석 실패: {e}")
        return {"technical_analysis": {"error": str(e)}, "errors": [f"technical_analysis: {str(e)}"]}


def news_analyst(state: AnalysisState) -> Dict[str, Any]:
    """뉴스 분석 전문가"""
    print("\n📰 [News Analyst] 뉴스 분석 시작...")
    
    llm = get_chat_model("gpt-4o")
    
    prompt = f"""당신은 뉴스 분석 전문가입니다.
종목: {state['company_name']} ({state['ticker']})
업종: {state['industry']}

다음 뉴스 데이터를 바탕으로 분석을 수행하세요:

**뉴스 데이터:**
{json.dumps(state.get('news_data', {}), ensure_ascii=False, indent=2)}

**출력 형식 (JSON):**
```json
{{
  "news_and_momentum": {{
    "recent_news_highlights": [
      {{"title": "뉴스 제목", "summary": "뉴스 요약"}}
    ],
    "sentiment": "positive",
    "sector_trend": "업종 트렌드 설명",
    "news_comment": "{state['company_name']} 관련 뉴스 분석 코멘트"
  }},
  "news_score": 68
}}
```

반드시 ```json 블록으로 감싸서 반환하세요."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        
        # JSON 추출
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
        if json_match:
            result = json.loads(json_match.group(1).strip())
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            result = json.loads(json_match.group(0).strip()) if json_match else {}
        
        print(f"   ✓ 뉴스 분석 완료 (점수: {result.get('news_score', 'N/A')})")
        return {"news_analysis": result}
    
    except Exception as e:
        print(f"   ❌ 뉴스 분석 실패: {e}")
        return {"news_analysis": {"error": str(e)}, "errors": [f"news_analysis: {str(e)}"]}


# =====================================================
# 통합 분석 노드
# =====================================================

def synthesizer(state: AnalysisState) -> Dict[str, Any]:
    """통합 분석가 - 모든 전문가 의견을 종합"""
    print("\n🎯 [Synthesizer] 최종 보고서 작성 중...")
    
    llm = get_chat_model("gpt-4o")
    
    # 각 전문가의 분석 결과
    financial = state.get('financial_analysis', {})
    technical = state.get('technical_analysis', {})
    news = state.get('news_analysis', {})
    
    prompt = f"""당신은 투자 전략 수립 전문가입니다.
세 명의 전문가 분석을 종합하여 최종 투자 보고서를 작성하세요.

종목: {state['company_name']} ({state['ticker']})
시장: {state['market']} | 업종: {state['industry']} | 시가총액: {state['market_cap_level']}
투자 성향: {state['profile']}

**재무 분석가 의견:**
{json.dumps(financial, ensure_ascii=False, indent=2)}

**기술적 분석가 의견:**
{json.dumps(technical, ensure_ascii=False, indent=2)}

**뉴스 분석가 의견:**
{json.dumps(news, ensure_ascii=False, indent=2)}

**최종 보고서 형식 (JSON):**
```json
{{
  "meta": {{
    "generated_at": "{datetime.now().isoformat()}",
    "ticker": "{state['ticker']}",
    "data_asof": "{datetime.now().strftime('%Y-%m-%d')}",
    "profile": "{state['profile']}"
  }},
  "basic_info": {{
    "ticker": "{state['ticker']}",
    "name_kr": "{state['company_name']}",
    "market": "{state['market']}",
    "industry": "{state['industry']}",
    "market_cap_level": "{state['market_cap_level']}",
    "summary_sentence": "종목 요약 (1-2문장)"
  }},
  "market_snapshot": {{ ... }},
  "financial_summary": {{ ... }},
  "quality_scores": {{
    "financial_score": {financial.get('financial_score', 0)},
    "technical_score": {technical.get('technical_score', 0)},
    "news_score": {news.get('news_score', 0)},
    "overall_score": 75,
    "score_comment": "점수에 대한 종합 설명"
  }},
  "technical_analysis": {{ ... }},
  "news_and_momentum": {{ ... }},
  "scenarios_1y": {{
    "bull_case": {{
      "description": "강세 시나리오",
      "expected_return_range": "15% ~ 35%"
    }},
    "base_case": {{
      "description": "기본 시나리오",
      "expected_return_range": "5% ~ 15%"
    }},
    "bear_case": {{
      "description": "약세 시나리오",
      "expected_return_range": "-10% ~ 0%"
    }},
    "scenario_comment": "시나리오 분석"
  }},
  "risks": {{
    "major_risks": [
      {{
        "title": "리스크 제목",
        "description": "리스크 설명",
        "severity": "high"
      }}
    ]
  }},
  "investment_thesis": {{
    "key_points": [
      "핵심 포인트 1",
      "핵심 포인트 2",
      "핵심 포인트 3"
    ],
    "long_form_summary": "{state['company_name']}에 대한 종합 투자 의견 (3-5문장)"
  }},
  "recommendation": {{
    "rating": "BUY",
    "time_horizon_months": 12,
    "confidence_level": "high",
    "target_price_range": "88,000 ~ 92,000",
    "stop_loss_hint": "70,000 근처 이탈 시 주의",
    "recommendation_comment": "투자 추천 코멘트"
  }},
  "appendix_data": {{ ... }}
}}
```

**중요:**
1. 각 전문가의 분석을 모두 반영하세요
2. 전문가 분석의 데이터를 그대로 사용하되, 필요시 보완하세요
3. overall_score는 세 점수의 가중평균으로 계산하세요
4. 반드시 완전한 JSON을 ```json 블록으로 반환하세요"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        
        # JSON 추출
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
        if json_match:
            result = json.loads(json_match.group(1).strip())
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            result = json.loads(json_match.group(0).strip()) if json_match else {}
        
        # 목표가 검증 및 수정
        try:
            current_price = result.get('market_snapshot', {}).get('current_price', 0)
            target_range = result.get('recommendation', {}).get('target_price_range', '')
            
            if current_price > 0 and target_range:
                numbers = re.findall(r'[\d,]+', target_range)
                if len(numbers) >= 2:
                    target_high = int(numbers[1].replace(',', ''))
                    
                    if target_high < current_price:
                        new_low = int(current_price * 1.10)
                        new_high = int(current_price * 1.20)
                        result['recommendation']['target_price_range'] = f"{new_low:,} ~ {new_high:,}"
                        print(f"   ⚠️ 목표가 수정: {target_range} → {result['recommendation']['target_price_range']}")
        except Exception:
            pass
        
        print(f"   ✓ 최종 보고서 작성 완료")
        return {"final_report": result}
    
    except Exception as e:
        print(f"   ❌ 최종 보고서 작성 실패: {e}")
        # 에러 시 fallback 결과 생성
        return {
            "final_report": {
                "error": str(e),
                "meta": {
                    "generated_at": datetime.now().isoformat(),
                    "ticker": state['ticker'],
                    "profile": state['profile']
                }
            },
            "errors": [f"synthesizer: {str(e)}"]
        }


# =====================================================
# Graph 구축
# =====================================================

def build_analysis_graph():
    """LangGraph 분석 그래프 구축"""
    
    workflow = StateGraph(AnalysisState)
    
    # 노드 추가
    # 1단계: 데이터 수집 (병렬)
    workflow.add_node("collect_price", collect_price_data)
    workflow.add_node("collect_financial", collect_financial_data)
    workflow.add_node("collect_technical", collect_technical_data)
    workflow.add_node("collect_news", collect_news_data)
    
    # 2단계: 전문가 분석 (병렬)
    workflow.add_node("financial_analyst", financial_analyst)
    workflow.add_node("technical_analyst", technical_analyst)
    workflow.add_node("news_analyst", news_analyst)
    
    # 3단계: 통합 분석
    workflow.add_node("synthesizer", synthesizer)
    
    # 엣지 설정
    # START -> 데이터 수집 (병렬)
    workflow.set_entry_point("collect_price")
    workflow.set_entry_point("collect_financial")
    workflow.set_entry_point("collect_technical")
    workflow.set_entry_point("collect_news")
    
    # 데이터 수집 -> 전문가 분석
    workflow.add_edge("collect_price", "financial_analyst")
    workflow.add_edge("collect_financial", "financial_analyst")
    
    workflow.add_edge("collect_technical", "technical_analyst")
    workflow.add_edge("collect_price", "technical_analyst")
    
    workflow.add_edge("collect_news", "news_analyst")
    
    # 전문가 분석 -> 통합 분석
    workflow.add_edge("financial_analyst", "synthesizer")
    workflow.add_edge("technical_analyst", "synthesizer")
    workflow.add_edge("news_analyst", "synthesizer")
    
    # 통합 분석 -> END
    workflow.add_edge("synthesizer", END)
    
    return workflow.compile()


# =====================================================
# 실행 함수
# =====================================================

def run_langgraph_stock_analysis(
    ticker: str,
    profile: Literal["aggressive", "balanced", "conservative"] = "balanced",
    model_name: str = "gpt-4o"
) -> Dict[str, Any]:
    """
    LangGraph 멀티 에이전트 분석 실행
    
    Args:
        ticker: 종목 코드
        profile: 투자 성향
        model_name: LLM 모델 이름
    
    Returns:
        분석 결과 JSON (기존과 동일한 구조)
    """
    
    print(f"\n{'='*60}")
    print(f"🔍 LangGraph 멀티 에이전트 분석 시작: {ticker}")
    print(f"{'='*60}\n")
    
    # 기본 정보 조회
    try:
        sql = "SELECT ticker, name_kr, market, industry FROM companies WHERE ticker = %s"
        company = fetch_one(sql, (ticker,))
        
        if company:
            company_name = company[1] or ticker
            market = company[2] or "KOSPI"
            industry_code = company[3]
            industry = INDUSTRY_CODE_MAP.get(industry_code, industry_code or "기타")
            
            # 시가총액 조회
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
            if market_cap > 10_000_000_000_000:
                market_cap_level = "대형주"
            elif market_cap > 1_000_000_000_000:
                market_cap_level = "중형주"
            else:
                market_cap_level = "소형주"
        else:
            company_name = ticker
            market = "KOSPI"
            industry = "기타"
            market_cap_level = "중형주"
    
    except Exception as e:
        print(f"⚠️ 기본 정보 조회 오류: {e}")
        company_name = ticker
        market = "KOSPI"
        industry = "기타"
        market_cap_level = "중형주"
    
    # 초기 상태
    initial_state = AnalysisState(
        ticker=ticker,
        company_name=company_name,
        market=market,
        industry=industry,
        market_cap_level=market_cap_level,
        profile=profile,
        price_data={},
        financial_data={},
        technical_data={},
        news_data={},
        financial_analysis={},
        technical_analysis={},
        news_analysis={},
        final_report={},
        messages=[],
        errors=[]
    )
    
    # Graph 실행
    graph = build_analysis_graph()
    
    print("🚀 Graph 실행 중...\n")
    result = graph.invoke(initial_state)
    
    print(f"\n{'='*60}")
    print("✅ 분석 완료")
    print(f"{'='*60}")
    
    # 에러 확인
    if result.get('errors'):
        print(f"\n⚠️ 발생한 에러:")
        for err in result['errors']:
            print(f"   - {err}")
    
    return result.get('final_report', {})


# =====================================================
# CLI 테스트
# =====================================================

if __name__ == "__main__":
    import sys
    
    ticker = sys.argv[1] if len(sys.argv) > 1 else "005930.KS"
    profile = sys.argv[2] if len(sys.argv) > 2 else "balanced"
    
    result = run_langgraph_stock_analysis(ticker=ticker, profile=profile)
    
    print("\n" + "="*60)
    print("📊 최종 분석 결과")
    print("="*60)
    print(json.dumps(result, ensure_ascii=False, indent=2))