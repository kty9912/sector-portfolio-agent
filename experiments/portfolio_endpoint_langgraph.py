"""
portfolio_endpoint_langgraph.py

LangGraph 기반 포트폴리오 분석 시스템 (FastAPI + UI)
기존 Anthropic 방식과 비교 가능하도록 별개로 구성
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import json
import re
import traceback
from plotly import graph_objects as go
from plotly.io import to_html
import io
import tempfile
# import pdfkit  # ⭐ 제거됨
from playwright.sync_api import sync_playwright
import concurrent.futures
from datetime import datetime

from agent_test.portfolio_agent_langgraph import (
    run_portfolio_agent_langgraph,
    AVAILABLE_STOCKS,
    SECTORS
)
from core.llm_clients import AVAILABLE_MODELS

app = FastAPI(title="AI 투자 포트폴리오 분석 시스템 v2 - LangGraph")


# =====================================================
# Request Model
# =====================================================

class InvestmentTargets(BaseModel):
    sectors: List[str] = Field(default=[], description="선택한 섹터 리스트")
    tickers: List[str] = Field(default=[], description="선택한 종목 티커 리스트")

class PortfolioRequest(BaseModel):
    budget: int = Field(..., ge=1000000, description="투자 예산")
    investment_targets: InvestmentTargets = Field(..., description="투자 대상 (섹터/종목)")
    risk_profile: Literal["안정", "중립", "공격"] = Field(..., description="투자 성향")
    investment_period: Literal["단기", "중기", "장기"] = Field(..., description="투자 기간")
    additional_prompt: Optional[str] = Field(default="", description="추가 요구사항")


# =====================================================
# API Endpoints
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_UI

@app.get("/api/sectors")
async def get_sectors():
    """사용 가능한 섹터 리스트"""
    return {"sectors": SECTORS}

@app.get("/api/stocks")
async def get_stocks():
    """전체 종목 리스트"""
    return {
        "stocks": [
            {"ticker": ticker, "name": name}
            for ticker, name in AVAILABLE_STOCKS
        ]
    }

@app.get("/api/models")
async def get_available_models():
    """사용 가능한 AI 모델 리스트 (LangGraph)"""
    # LangGraph는 더 많은 모델을 지원할 수 있음
    langgraph_models = AVAILABLE_MODELS + ['gpt-4o', 'gpt-4o-mini']
    unique_models = list(set(langgraph_models))  # 중복 제거
    
    return {
        "models": unique_models,
        "default_model": unique_models[0] if unique_models else "No Models Available"
    }

@app.post("/api/analyze")
async def analyze_portfolio(request: PortfolioRequest):
    """포트폴리오 분석 실행 (LangGraph)"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 LangGraph 분석 요청:")
        print(f"  예산: {request.budget:,}원")
        print(f"  섹터: {request.investment_targets.sectors}")
        print(f"  종목: {request.investment_targets.tickers}")
        print(f"  성향: {request.risk_profile}")
        print(f"  기간: {request.investment_period}")
        print(f"{'='*60}\n")
        
        result = run_portfolio_agent_langgraph(
            budget=request.budget,
            investment_targets={
                "sectors": request.investment_targets.sectors,
                "tickers": request.investment_targets.tickers
            },
            risk_profile=request.risk_profile,
            investment_period=request.investment_period,
            additional_prompt=request.additional_prompt
        )
        
        if result["success"]:
            # ⭐ 디버깅: 반환된 데이터 확인
            print(f"\n{'='*60}")
            print(f"🔍 [디버깅] Agent 반환 데이터:")
            print(f"{'='*60}")
            print(f"✓ ai_summary 길이: {len(result.get('ai_summary', '')) if result.get('ai_summary') else 0} 글자")
            print(f"✓ portfolio_allocation 개수: {len(result.get('portfolio_allocation', []))}")
            
            # portfolio_allocation 상세 확인
            if result.get('portfolio_allocation'):
                print(f"\n📊 포트폴리오 상세:")
                for i, stock in enumerate(result.get('portfolio_allocation', [])):
                    print(f"\n  [{i+1}] {stock.get('name')} ({stock.get('ticker')})")
                    print(f"      - weight: {stock.get('weight')}")
                    print(f"      - amount: {stock.get('amount')}")
                    print(f"      - scores: {stock.get('scores')}")
            else:
                print(f"\n❌ portfolio_allocation이 비어있습니다!")
            
            print(f"\n✓ performance_metrics: {result.get('performance_metrics')}")
            print(f"✓ chart_data: {result.get('chart_data')}")
            print(f"{'='*60}\n")
            
            # ⭐ 데이터 구조를 portfolio_endpoint.py와 동일하게 변환
            data = {
                "ai_summary": result.get("ai_summary"),
                "portfolio_allocation": result.get("portfolio_allocation"),
                "performance_metrics": result.get("performance_metrics"),
                "chart_data": result.get("chart_data")
            }
            
            # ⭐ Sunburst 차트 생성
            sunburst_chart, chart_config = create_sunburst_chart(data)
            
            # 차트를 HTML로 변환
            chart_html = to_html(
                sunburst_chart, 
                include_plotlyjs='cdn',
                full_html=False,
                div_id="sectorChart"
            )
            
            print(f"[DEBUG] chart_html 생성됨, 길이: {len(chart_html)}")
            
            # ⭐ chart_data 구조 생성 (수익률 차트용)
            chart_data = {}
            
            # 기존 데이터에서 수익률 정보 추출
            # 1차: data.chart_data.expected_performance 확인
            if (data.get('chart_data', {}).get('expected_performance') and 
                'months' in data['chart_data']['expected_performance'] and
                'portfolio' in data['chart_data']['expected_performance'] and
                'benchmark' in data['chart_data']['expected_performance']):
                
                existing_perf = data['chart_data']['expected_performance']
                chart_data['expected_performance'] = {
                    'months': existing_perf['months'],
                    'portfolio': existing_perf['portfolio'], 
                    'benchmark': existing_perf['benchmark']
                }
                print(f"✅ data.chart_data.expected_performance에서 추출: {chart_data['expected_performance']}")
                
            # 2차: data 직접 확인 (기존 구조)
            elif 'months' in data and 'portfolio' in data and 'benchmark' in data:
                chart_data['expected_performance'] = {
                    'months': data['months'],
                    'portfolio': data['portfolio'], 
                    'benchmark': data['benchmark']
                }
                print(f"✅ data 직접 접근으로 추출: {chart_data['expected_performance']}")
                
            else:
                # 수익률 데이터가 없는 경우 null로 설정
                chart_data['expected_performance'] = None
                print("⚠️ 수익률 데이터 없음 - 차트 비활성화")
            
            # ⭐ sunburst 데이터 검증 및 생성
            if data.get('chart_data', {}).get('sunburst'):
                print("✅ LLM에서 sunburst 데이터 제공됨")
            else:
                print("⚠️ sunburst 데이터 누락 - 포트폴리오 구성으로 자동 생성")
                # portfolio_allocation에서 sunburst 데이터 자동 생성
                if data.get('portfolio_allocation'):
                    sunburst_data = []
                    sector_weights = {}
                    
                    # 섹터별 가중치 합계 계산
                    for stock in data['portfolio_allocation']:
                        sector = stock.get('sector', '기타')
                        weight = stock.get('weight', 0)
                        if sector not in sector_weights:
                            sector_weights[sector] = 0
                        sector_weights[sector] += weight
                    
                    # 섹터 노드 추가
                    for sector, weight in sector_weights.items():
                        sunburst_data.append({
                            "name": sector,
                            "value": weight
                        })
                    
                    # 종목 노드 추가
                    for stock in data['portfolio_allocation']:
                        sunburst_data.append({
                            "name": stock.get('name', stock.get('ticker')),
                            "value": stock.get('weight', 0),
                            "parent": stock.get('sector', '기타')
                        })
                    
                    # chart_data에 추가
                    if 'chart_data' not in data:
                        data['chart_data'] = {}
                    data['chart_data']['sunburst'] = sunburst_data
                    print(f"✅ sunburst 데이터 자동 생성 완료: {len(sunburst_data)}개 노드")
            
            # 데이터에 차트 HTML과 설정 추가
            data['chart_html'] = chart_html
            data['chart_config'] = chart_config
            data['chart_data'] = chart_data
            
            return JSONResponse(content={
                "success": True,
                "report": json.dumps(data, ensure_ascii=False),
                "iterations": 1
            })
        else:
            print(f"❌ 분석 실패: {result}")
            raise HTTPException(status_code=500, detail=result.get("error", "알 수 없는 오류"))
    
    except Exception as e:
        print(f"\n❌ 서버 오류:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


@app.post("/api/export-pdf")
async def export_pdf(request: dict):
    """포트폴리오 분석 결과를 PDF로 내보내기 (LangGraph)"""
    try:
        print("\n📄 PDF 생성 시작...")
        
        html_content = request.get('html_content', '')
        
        if not html_content:
            raise HTTPException(status_code=400, detail="HTML 콘텐츠가 없습니다")
        
        # ⭐ Windows 호환 PDF 생성 (sync_playwright 사용)
        def generate_pdf_sync():
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # HTML 콘텐츠 설정
                page.set_content(html_content)
                
                # PDF 생성 (⭐ 세로 모드, 작은 여백)
                pdf_bytes = page.pdf(
                    format='A4',
                    landscape=False,  # ⭐ 세로 모드
                    margin={
                        'top': '10mm',
                        'bottom': '10mm', 
                        'left': '10mm',
                        'right': '10mm'
                    },
                    print_background=True
                )
                
                browser.close()
                return pdf_bytes
        
        # ThreadPoolExecutor로 실행 (Windows 호환성)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(generate_pdf_sync)
            pdf_bytes = future.result(timeout=30)
        
        print("✅ PDF 생성 완료")
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=portfolio_analysis_langgraph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
        )
        
    except Exception as e:
        print(f"❌ PDF 생성 오류: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


def create_sunburst_chart(data):
    """3단계 구조의 완전한 원형 Sunburst 차트 생성 (LangGraph)"""
    
    portfolio = data.get('portfolio_allocation', [])
    
    if not portfolio:
        print("⚠️ portfolio_allocation이 비어있습니다")
        # 빈 차트 반환
        fig_sunburst = go.Figure()
        fig_sunburst.add_trace(go.Sunburst(
            labels=['데이터 없음'],
            parents=[''],
            values=[100],
            marker=dict(colors=['#cccccc'])
        ))
        return fig_sunburst, {}
    
    # 색상 매핑 (LangGraph 전용 색상)
    colorMap = {
        '반도체': '#667eea',  # LangGraph 메인 색상
        '바이오': '#764ba2',
        '방산': '#f093fb',
        '통신': '#4facfe',
        '원자력': '#43e97b',
        '전력망': '#fa709a',
        '조선': '#fee140',
        'AI': '#FF6B9D',
        '기타': '#30cfd0'
    }
    
    def lighten_color(hex_color, brightness_level=0):
        """색상을 밝게 만드는 함수"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        if brightness_level == 1:
            factor = 1.3
        elif brightness_level == 2:
            factor = 1.6
        else:
            factor = 1.0
        
        rgb = tuple(min(255, int(c * factor)) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    
    # 데이터 구조 생성
    labels = []
    parents = []
    values = []
    colors = []
    
    # 섹터별 그룹화
    sector_map = {}
    for stock in portfolio:
        sector = stock.get('sector', '기타')
        if sector not in sector_map:
            sector_map[sector] = []
        sector_map[sector].append(stock)
    
    print(f"섹터 맵: {list(sector_map.keys())}")
    
    # === 3단계 구조: 포트폴리오 → 섹터 → 종목 ===
    
    # 1. 루트 노드 "포트폴리오" 추가
    total_portfolio_value = sum((stock.get('weight', 0) * 100) for stock in portfolio)
    labels.append('포트폴리오')
    parents.append('')  # 최상위 루트
    values.append(total_portfolio_value)
    colors.append('#FFFFFF')  # 포트폴리오 색상 (흰색)
    
    print(f"포트폴리오 총 비중: {total_portfolio_value:.1f}%")
    
    # 2. 섹터들 추가 (부모: 포트폴리오)
    for sector, stocks in sector_map.items():
        sector_weight = sum(stock.get('weight', 0) * 100 for stock in stocks)
        labels.append(sector)
        parents.append('포트폴리오')
        values.append(sector_weight)
        colors.append(colorMap.get(sector, '#30cfd0'))
        
        print(f"섹터 {sector}: {sector_weight:.1f}%")
    
    # 3. 종목들 추가 (부모: 각 섹터)
    sector_stock_index = {}
    for sector, stocks in sector_map.items():
        sector_stock_index[sector] = 0
        for stock in stocks:
            stock_weight = stock.get('weight', 0) * 100
            stock_name = stock.get('name', stock.get('ticker', 'Unknown'))
            
            labels.append(stock_name)
            parents.append(sector)
            values.append(stock_weight)
            
            # 종목 색상: 섹터 색상을 기반으로 밝기 조절
            base_color = colorMap.get(sector, '#30cfd0')
            stock_color = lighten_color(base_color, sector_stock_index[sector] % 3)
            colors.append(stock_color)
            
            sector_stock_index[sector] += 1
            
            print(f"  종목 {stock_name}: {stock_weight:.1f}%")
    
    print(f"\n차트 데이터:")
    print(f"  labels 개수: {len(labels)}")
    print(f"  parents 개수: {len(parents)}")
    print(f"  values 개수: {len(values)}")
    print(f"  colors 개수: {len(colors)}")
    
    # Plotly Sunburst 차트 생성
    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        ids=labels,  # 고유 ID 설정
        branchvalues='total',  # ⭐ 완전한 원형을 위해 'total' 사용
        marker=dict(
            colors=colors,
            line=dict(color='white', width=2)
        ),
        textinfo='label',  # ⭐ 라벨만 표시
        hovertemplate='<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
        textfont=dict(size=12, color='black', family='Pretendard, Arial, sans-serif'),
        maxdepth=3,  # 3단계 모두 표시
        rotation=0,   # 회전 고정
        sort=False    # 정렬 비활성화
    ))
    
    # 레이아웃 설정 (⭐ 크기 조정: 470px 컨테이너에 맞춤)
    fig.update_layout(
        margin=dict(t=10, l=10, r=10, b=10),
        width=430,   # ⭐ 430px 차트 크기
        height=430,  # ⭐ 430px 차트 크기
        font=dict(family='Pretendard, Arial, sans-serif', size=12),
        paper_bgcolor='rgba(0,0,0,0)',  # 투명 배경
        plot_bgcolor='rgba(0,0,0,0)'    # 투명 배경
    )
    
    # 차트 설정 반환
    chart_config = {
        'total_portfolio_value': total_portfolio_value,
        'sector_count': len(sector_map),
        'stock_count': len(portfolio)
    }
    
    print(f"✅ Sunburst 차트 생성 완료: {chart_config}")
    
    return fig, chart_config


# =====================================================
# HTML UI (기존과 동일하되, LangGraph 표시)
# =====================================================

HTML_UI = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 투자 포트폴리오 분석 v2 - LangGraph</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .version-badge {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-top: 10px;
            font-weight: 600;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 450px 1fr;
            gap: 20px;
        }
        
        .panel {
            background: white;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        
        .input-panel {
            height: fit-content;
            position: sticky;
            top: 20px;
        }
        
        .panel h2 {
            color: #764ba2;
            margin-bottom: 20px;
            font-size: 1.4em;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
            font-size: 0.95em;
        }
        
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #764ba2;
        }
        
        .form-group textarea {
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .tab {
            padding: 10px 20px;
            background: #f0f0f0;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .tab.active {
            background: #764ba2;
            color: white;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .selection-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            max-height: 250px;
            overflow-y: auto;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        
        .selection-item {
            display: flex;
            align-items: center;
            padding: 10px;
            background: white;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .selection-item:hover {
            background: #e9ecef;
            transform: translateY(-1px);
        }
        
        .selection-item input {
            width: auto;
            margin-right: 10px;
            cursor: pointer;
        }
        
        .selection-item label {
            cursor: pointer;
            margin: 0;
            font-weight: normal;
            font-size: 0.9em;
        }
        
        .selected-count {
            font-size: 0.85em;
            color: #764ba2;
            margin-top: 10px;
            font-weight: 600;
        }
        
        .btn-primary {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn-primary:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(118, 75, 162, 0.4);
        }
        
        .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .result-panel {
            min-height: 800px;
        }
        
        .loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 400px;
        }
        
        .spinner {
            width: 60px;
            height: 60px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #764ba2;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .empty-state {
            text-align: center;
            color: #999;
            padding: 80px 20px;
        }
        
        .empty-state svg {
            width: 120px;
            height: 120px;
            margin-bottom: 20px;
            opacity: 0.3;
        }
        
        .result-content {
            display: none;
        }
        
        .result-content.active {
            display: block;
        }
        
        .section {
            margin-bottom: 30px;
        }
        
        .section-title {
            font-size: 1.3em;
            color: #764ba2;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #764ba2;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .summary-box {
            background: linear-gradient(135deg, #764ba215 0%, #667eea15 100%);
            border-left: 4px solid #764ba2;
            padding: 20px;
            border-radius: 10px;
            font-size: 1.05em;
            line-height: 1.8;
            color: #333;
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .metric-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s;
        }
        
        .metric-card:hover {
            border-color: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        .metric-label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 8px;
        }
        
        .metric-value {
            font-size: 2em;
            font-weight: 700;
            color: #764ba2;
        }
        
        .metric-unit {
            font-size: 0.5em;
            color: #999;
        }
        
        .chart-container {
            position: relative;
            height: 470px;  /* ⭐ 컨테이너 크기 조정 */
            margin: 20px 0;
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

        /* 화면에서는 세로로, PDF에서는 가로로 배치 */
        .charts-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin: 20px 0;
        }

        .chart-wrapper {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

        /* 큰 화면에서는 나란히 배치 */
        @media (min-width: 1200px) {
            .charts-container {
                flex-direction: row;
            }
            .chart-wrapper {
                flex: 1;
            }
        }
        
        .stock-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        
        .stock-table th {
            background: #f8f9fa;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }
        
        .stock-table td {
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
            font-size: 0.95em;
        }
        
        .stock-table td:nth-child(2) .score-bar {
            max-width: 80px;
        }
        
        .stock-table tr:last-child td {
            border-bottom: none;
        }
        
        .stock-table tr:hover {
            background: #f8f9fa;
        }
        
        .score-bar {
            width: 100%;
            height: 8px;
            background: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
            max-width: 100px;
        }
        
        .score-fill {
            height: 100%;
            background: linear-gradient(90deg, #764ba2 0%, #667eea 100%);
            transition: width 0.5s ease;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        .badge-sector {
            background: #f0e7ff;
            color: #764ba2;
        }
        
        @media (max-width: 1200px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            .input-panel {
                position: static;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AI 투자 포트폴리오 분석 시스템</h1>
            <div class="version-badge">⚡ LangGraph 버전</div>
            <p>고도화된 데이터 기반 투자 전략 분석</p>
        </div>
        
        <div class="main-content">
            <!-- 입력 패널 -->
            <div class="panel input-panel">
                <h2>📝 투자 조건 입력</h2>
                
                <form id="portfolioForm">
                    <!-- 1. 투자 예산 -->
                    <div class="form-group">
                        <label>💰 총 투자 예산 (원)</label>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <input type="number" id="budgetInput" name="budget" value="5000000" 
                                   min="1000000" step="10000" required
                                   style="flex: 1; font-size: 1.05em; text-align: right;">
                            <span id="budgetDisplay" style="min-width: 140px; font-weight: 600; color: #764ba2; text-align: right; padding: 12px 15px; background: #f8f9fa; border-radius: 8px; border: 2px solid #e9ecef; font-size: 1.1em; white-space: nowrap;">
                                5백만원
                            </span>
                        </div>
                    </div>
                    
                    <!-- 2. 투자 대상 -->
                    <div class="form-group">
                        <label>🎯 투자 대상</label>
                        <div class="tabs">
                            <button type="button" class="tab active" data-tab="sectors">섹터 선택</button>
                            <button type="button" class="tab" data-tab="stocks">종목 선택</button>
                        </div>
                        
                        <div id="sectors-tab" class="tab-content active">
                            <div class="selection-grid" id="sectorsList"></div>
                            <div class="selected-count" id="sectorsCount">선택: 0개</div>
                        </div>
                        
                        <div id="stocks-tab" class="tab-content">
                            <div class="selection-grid" id="stocksList"></div>
                            <div class="selected-count" id="stocksCount">선택: 0개</div>
                        </div>
                    </div>
                    
                    <!-- 3. 투자 성향 -->
                    <div class="form-group">
                        <label>⚖️ 투자 위험 성향</label>
                        <select name="risk_profile" required>
                            <option value="안정">안정 (낮은 변동성, 안전 자산 선호)</option>
                            <option value="중립">중립 (균형 잡힌 포트폴리오)</option>
                            <option value="공격" selected>공격 (높은 수익률 추구)</option>
                        </select>
                    </div>
                    
                    <!-- 4. 투자 기간 -->
                    <div class="form-group">
                        <label>📅 투자 기간</label>
                        <select name="investment_period" required>
                            <option value="단기">단기 (3개월 이하)</option>
                            <option value="중기" selected>중기 (3개월~12개월)</option>
                            <option value="장기">장기 (1년 이상)</option>
                        </select>
                    </div>
                    
                    <!-- 5. 추가 프롬프트 -->
                    <div class="form-group">
                        <label>💬 추가 요구사항 (선택)</label>
                        <textarea name="additional_prompt" 
                                  placeholder="예: ESG 점수가 높은 종목 우선, 배당 수익 중시 등"></textarea>
                    </div>
                    
                    <button type="submit" class="btn-primary" id="analyzeBtn">
                        🚀 포트폴리오 분석 시작
                    </button>
                </form>
            </div>
            
            <!-- 결과 패널 -->
            <div class="panel result-panel">
                <h2>📊 분석 결과</h2>
                
                <div id="emptyState" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/>
                    </svg>
                    <h3>투자 조건을 입력하세요</h3>
                    <p>LangGraph AI가 최적의 포트폴리오를 분석합니다</p>
                </div>
                
                <div id="loadingState" class="loading" style="display: none;">
                    <div class="spinner"></div>
                    <h3>LangGraph가 포트폴리오를 분석하고 있습니다...</h3>
                    <p style="margin-top: 10px; color: #666;">
                        [초기화] → [데이터 수집] → [분석] → [검증] → 완료
                    </p>
                </div>
                
                <div id="resultContent" class="result-content"></div>
            </div>
        </div>
    </div>
    
    <script>
        // 동일한 JavaScript 코드 (UI는 동일, 성능만 다름)
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`${tabName}-tab`).classList.add('active');
            });
        });
        
        async function loadSectors() {
            const response = await fetch('/api/sectors');
            const data = await response.json();
            const sectorsList = document.getElementById('sectorsList');
            sectorsList.innerHTML = data.sectors.map(sector => `
                <div class="selection-item">
                    <input type="checkbox" id="sector_${sector}" name="sectors" value="${sector}" onchange="updateCount('sectors')">
                    <label for="sector_${sector}">${sector}</label>
                </div>
            `).join('');
        }
        
        async function loadStocks() {
            const response = await fetch('/api/stocks');
            const data = await response.json();
            const stocksList = document.getElementById('stocksList');
            stocksList.innerHTML = data.stocks.map(stock => `
                <div class="selection-item">
                    <input type="checkbox" id="stock_${stock.ticker}" name="stocks" value="${stock.ticker}" onchange="updateCount('stocks')">
                    <label for="stock_${stock.ticker}">${stock.name}</label>
                </div>
            `).join('');
        }
        
        function updateCount(type) {
            const count = document.querySelectorAll(`input[name="${type}"]:checked`).length;
            document.getElementById(`${type}Count`).textContent = `선택: ${count}개`;
        }
        
        document.getElementById('portfolioForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const selectedSectors = Array.from(document.querySelectorAll('input[name="sectors"]:checked')).map(cb => cb.value);
            const selectedStocks = Array.from(document.querySelectorAll('input[name="stocks"]:checked')).map(cb => cb.value);
            
            if (selectedSectors.length === 0 && selectedStocks.length === 0) {
                alert('섹터 또는 종목을 최소 1개 이상 선택해주세요.');
                return;
            }
            
            const requestData = {
                budget: parseInt(formData.get('budget')),
                investment_targets: {sectors: selectedSectors, tickers: selectedStocks},
                risk_profile: formData.get('risk_profile'),
                investment_period: formData.get('investment_period'),
                additional_prompt: formData.get('additional_prompt') || ""
            };
            
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('loadingState').style.display = 'flex';
            document.getElementById('resultContent').classList.remove('active');
            document.getElementById('analyzeBtn').disabled = true;
            
            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(requestData)
                });
                const result = await response.json();
                if (result.success) {
                    console.log('[DEBUG] 서버 응답:', result);
                    console.log('[DEBUG] result.report 타입:', typeof result.report);
                    
                    // result.report가 이미 객체인지 문자열인지 확인
                    let reportData = result.report;
                    if (typeof reportData === 'string') {
                        try {
                            reportData = JSON.parse(reportData);
                            console.log('[DEBUG] JSON.parse 성공');
                        } catch (e) {
                            console.error('[DEBUG] JSON.parse 실패:', e);
                        }
                    }
                    
                    renderResults(reportData, result.iterations);
                } else {
                    throw new Error(result.detail || '분석 실패');
                }
            } catch (error) {
                document.getElementById('resultContent').innerHTML = `
                    <div style="background: #fee; border: 2px solid #fcc; border-radius: 12px; padding: 30px; color: #c33;">
                        <h3>❌ 오류 발생</h3>
                        <p style="margin-top: 10px;">${error.message}</p>
                    </div>
                `;
                document.getElementById('resultContent').classList.add('active');
            } finally {
                document.getElementById('loadingState').style.display = 'none';
                document.getElementById('analyzeBtn').disabled = false;
            }
        });
        
        // renderResults 함수 (완전한 버전)
        function renderResults(reportData, iterations) {
            console.log('[DEBUG] renderResults 호출됨');
            console.log('[DEBUG] reportData 타입:', typeof reportData);
            console.log('[DEBUG] reportData:', reportData);
            
            let data = null;
            
            // 1단계: 이미 JSON 객체인지 확인
            if (typeof reportData === 'object' && reportData !== null) {
                console.log('[DEBUG] reportData는 이미 객체입니다');
                data = reportData;
            }
            // 2단계: JSON 문자열 파싱 시도
            else if (typeof reportData === 'string') {
                console.log('[DEBUG] reportData 길이:', reportData.length);
                console.log('[DEBUG] reportData 첫 200자:', reportData.substring(0, 200));
                
                try {
                    // 2-1: ```json 블록에서 추출
                    const jsonMatch = reportData.match(/```json\s*([\s\S]*?)\s*```/);
                    if (jsonMatch) {
                        console.log('[DEBUG] ```json 블록 발견');
                        data = JSON.parse(jsonMatch[1]);
                        console.log('[DEBUG] ```json 블록 파싱 성공');
                    }
                    // 2-2: 직접 JSON 파싱
                    else {
                        console.log('[DEBUG] 직접 JSON 파싱 시도');
                        data = JSON.parse(reportData);
                        console.log('[DEBUG] 직접 JSON 파싱 성공');
                    }
                } catch (e) {
                    console.error('[DEBUG] JSON 파싱 오류:', e);
                    console.log('[DEBUG] 원본 텍스트 표시로 fallback');
                    
                    document.getElementById('resultContent').innerHTML = `
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 12px;">
                            <h3>📊 분석 결과 (원본)</h3>
                            <pre style="white-space: pre-wrap; word-wrap: break-word; background: white; padding: 15px; border-radius: 8px; font-size: 13px; line-height: 1.4;">${reportData}</pre>
                        </div>
                    `;
                    document.getElementById('resultContent').classList.add('active');
                    return;
                }
            }
            
            if (!data) {
                console.error('[DEBUG] 최종 데이터 파싱 실패');
                document.getElementById('resultContent').innerHTML = `
                    <div style="background: #fee; border: 2px solid #fcc; border-radius: 12px; padding: 30px; color: #c33;">
                        <h3>❌ 데이터 파싱 실패</h3>
                        <p style="margin-top: 10px;">분석 결과를 표시할 수 없습니다.</p>
                        <details style="margin-top: 15px;">
                            <summary>디버그 정보</summary>
                            <pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 10px; font-size: 12px;">
데이터 타입: ${typeof reportData}
데이터 내용: ${JSON.stringify(reportData, null, 2)}
                            </pre>
                        </details>
                    </div>
                `;
                document.getElementById('resultContent').classList.add('active');
                return;
            }
            
            console.log('[DEBUG] 최종 파싱된 data:', data);

            
            let html = `<div style="color: #28a745; margin-bottom: 25px; font-weight: 600; font-size: 1.05em;">
                ✅ LangGraph 분석 완료
            </div>`;
            
            // 1. AI 종합 요약
            if (data.ai_summary) {
                html += `
                    <div class="section">
                        <div class="section-title">🎯 AI 종합 브리핑</div>
                        <div class="summary-box">${data.ai_summary}</div>
                    </div>
                `;
            }
            
            // 2. 성과 지표
            if (data.performance_metrics) {
                const pm = data.performance_metrics;
                html += `
                    <div class="section">
                        <div class="section-title">📈 예상 성과 지표</div>
                        <div class="metrics-grid">
                            <div class="metric-card">
                                <div class="metric-label">예상 수익률</div>
                                <div class="metric-value">${pm.expected_return || 0}<span class="metric-unit">%</span></div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">최대 낙폭 (MDD)</div>
                                <div class="metric-value" style="color: #dc3545;">${pm.max_drawdown || 0}<span class="metric-unit">%</span></div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">샤프 비율</div>
                                <div class="metric-value">${pm.sharpe_ratio || 0}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">벤치마크 초과수익</div>
                                <div class="metric-value">${pm.benchmark_alpha || 0}<span class="metric-unit">%p</span></div>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            // 3. 추천 종목 종합표
            if (data.portfolio_allocation && data.portfolio_allocation.length > 0) {
                html += `
                    <div class="section">
                        <div class="section-title">💼 추천 종목 종합표</div>
                        <table class="stock-table">
                            <thead>
                                <tr>
                                    <th>종목명</th>
                                    <th>섹터</th>
                                    <th>비중</th>
                                    <th>투자금액</th>
                                    <th>주식수</th>
                                    <th>현재가</th>
                                    <th>목표가</th>
                                    <th>손절가</th>
                                    <th>종합점수</th>
                                </tr>
                            </thead>
                            <tbody>
                `;
                
                data.portfolio_allocation.forEach(stock => {
                    const avgScore = stock.scores ? 
                        Math.round((stock.scores.data_analysis + stock.scores.financial + stock.scores.news) / 3) : 0;
                    
                    html += `
                        <tr>
                            <td><strong>${stock.name || stock.ticker}</strong></td>
                            <td><span class="badge badge-sector">${stock.sector}</span></td>
                            <td><strong>${(stock.weight * 100).toFixed(1)}%</strong></td>
                            <td>${(stock.amount || 0).toLocaleString()}원</td>
                            <td>${stock.shares || 0}주</td>
                            <td>${(stock.current_price || 0).toLocaleString()}원</td>
                            <td style="color: #28a745; font-weight: 600;">${(stock.target_price || 0).toLocaleString()}원</td>
                            <td style="color: #dc3545; font-weight: 600;">${(stock.stop_loss || 0).toLocaleString()}원</td>
                            <td>
                                <div style="font-weight: 600; margin-bottom: 5px;">${avgScore}점</div>
                                <div class="score-bar">
                                    <div class="score-fill" style="width: ${avgScore}%"></div>
                                </div>
                            </td>
                        </tr>
                    `;
                });
                
                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }
            
            // 4. 점수 상세
            if (data.portfolio_allocation && data.portfolio_allocation.length > 0) {
                html += `
                    <div class="section">
                        <div class="section-title">🎯 종목별 점수 분석</div>
                        <table class="stock-table">
                            <thead>
                                <tr>
                                    <th>종목명</th>
                                    <th>데이터 분석 점수</th>
                                    <th>재무 점수</th>
                                    <th>뉴스 점수</th>
                                    <th>평균</th>
                                </tr>
                            </thead>
                            <tbody>
                `;
                
                data.portfolio_allocation.forEach(stock => {
                    if (stock.scores) {
                        const avgScore = Math.round((stock.scores.data_analysis + stock.scores.financial + stock.scores.news) / 3);
                        html += `
                            <tr>
                                <td><strong>${stock.name} <span style="color: #999; font-weight: normal; font-size: 0.9em;">(${stock.ticker})</span></strong></td>
                                <td>
                                    <div>${stock.scores.data_analysis}점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ${stock.scores.data_analysis}%"></div>
                                    </div>
                                </td>
                                <td>
                                    <div>${stock.scores.financial}점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ${stock.scores.financial}%"></div>
                                    </div>
                                </td>
                                <td>
                                    <div>${stock.scores.news}점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ${stock.scores.news}%"></div>
                                    </div>
                                </td>
                                <td><strong style="color: #764ba2; font-size: 1.1em;">${avgScore}점</strong></td>
                            </tr>
                        `;
                    }
                });
                
                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }
            
            // 5 & 6. 차트들을 한 섹션에 나란히 배치 (PDF에서 같은 페이지에 표시)
            if ((data.portfolio_allocation && data.portfolio_allocation.length > 0) || 
                (data.chart_data && data.chart_data.expected_performance)) {
                html += `
                    <div class="section">
                        <div class="section-title">📊 포트폴리오 분석 차트</div>
                        <div class="charts-container">
                `;
                
                if (data.portfolio_allocation && data.portfolio_allocation.length > 0) {
                    html += `
                        <div class="chart-wrapper">
                            <h4 style="color: #667eea; margin-bottom: 10px; text-align: center;">🥧 섹터별 포트폴리오 구성</h4>
                            <div id="sectorChart" style="height: 280px;"></div>
                        </div>
                    `;
                }
                
                if (data.chart_data && data.chart_data.expected_performance) {
                    html += `
                        <div class="chart-wrapper">
                            <h4 style="color: #667eea; margin-bottom: 10px; text-align: center;">� 예상 수익률 추이</h4>
                            <div id="performanceChart" style="height: 280px;"></div>
                        </div>
                    `;
                }
                
                html += `
                        </div>
                    </div>
                `;
            }
            
            // ⭐ PDF 내보내기 버튼 추가
            html += `
                <div class="section">
                    <div style="text-align: center; padding: 20px;">
                        <button onclick="exportToPDF()" style="
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            border: none;
                            padding: 15px 30px;
                            border-radius: 25px;
                            font-size: 16px;
                            font-weight: 600;
                            cursor: pointer;
                            transition: all 0.3s;
                            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
                        " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 8px 25px rgba(102, 126, 234, 0.4)'" 
                           onmouseout="this.style.transform='translateY(0px)'; this.style.boxShadow='0 4px 15px rgba(102, 126, 234, 0.3)'">
                            📄 PDF로 내보내기
                        </button>
                    </div>
                </div>
            `;
            
            document.getElementById('resultContent').innerHTML = html;
            document.getElementById('resultContent').classList.add('active');
            
            // 차트 렌더링
            renderCharts(data);
        }
        
        function renderCharts(data) {
            console.log('[DEBUG] renderCharts 시작');
            console.log('[DEBUG] data.chart_html 존재:', !!data.chart_html);
            console.log('[DEBUG] data.chart_config 존재:', !!data.chart_config);
            console.log('[DEBUG] data.portfolio_allocation 개수:', data.portfolio_allocation?.length || 0);
            
            // 1. 섹터 비중 Sunburst 차트 렌더링
            const chartElement = document.getElementById('sectorChart');
            if (!chartElement) {
                console.error('❌ sectorChart 요소를 찾을 수 없습니다');
                return;
            }

            // Plotly 라이브러리 확인
            if (typeof window.Plotly === 'undefined') {
                console.warn('⚠️ Plotly 라이브러리가 로드되지 않았습니다. 로딩을 기다립니다...');
                setTimeout(() => renderCharts(data), 500); // 0.5초 후 재시도
                return;
            }
            
            // 방법 1: chart_html 직접 삽입 (우선)
            if (data.chart_html && data.chart_html.trim()) {
                console.log('[DEBUG] chart_html 직접 삽입');
                chartElement.innerHTML = data.chart_html;
                
                // Plotly 차트가 삽입되면 리사이즈
                setTimeout(() => {
                    try {
                        const plotlyDiv = chartElement.querySelector('.plotly-graph-div');
                        if (plotlyDiv && window.Plotly) {
                            window.Plotly.Plots.resize(plotlyDiv);
                            console.log('✅ Plotly 차트 리사이즈 완료');
                        }
                    } catch (e) {
                        console.warn('⚠️ Plotly 리사이즈 실패:', e);
                    }
                }, 200);
            }
            // 방법 2: portfolio_allocation에서 직접 생성 (백업)
            else if (data.portfolio_allocation && data.portfolio_allocation.length > 0) {
                console.log('[DEBUG] portfolio_allocation으로 차트 생성');
                createSunburstFromData(data.portfolio_allocation);
            }
            // 방법 3: 차트 없음 메시지
            else {
                console.warn('[DEBUG] 차트 데이터 없음');
                chartElement.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;">
                        <div style="text-align: center;">
                            <div style="font-size: 48px; margin-bottom: 10px; opacity: 0.3;">📊</div>
                            <p>차트 데이터를 불러올 수 없습니다</p>
                        </div>
                    </div>
                `;
            }
            
            // 2. 수익률 차트 렌더링
            setTimeout(() => {
            renderPerformanceChart(data);
        }, 100);
    }
    
    // ⭐ Sunburst 차트를 직접 생성하는 함수 (백업용)
    function createSunburstFromData(portfolio) {
        console.log('[DEBUG] createSunburstFromData 호출됨, portfolio:', portfolio);
        
        if (!portfolio || portfolio.length === 0) {
            console.error('❌ portfolio_allocation이 비어있습니다');
            const chartElement = document.getElementById('sectorChart');
            if (chartElement) {
                chartElement.innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">포트폴리오 데이터가 없습니다</div>';
            }
            return;
        }

        // Plotly 라이브러리 재확인
        if (typeof window.Plotly === 'undefined') {
            console.error('❌ Plotly 라이브러리를 찾을 수 없습니다');
            setTimeout(() => createSunburstFromData(portfolio), 1000);
            return;
        }
        
        const colorMap = {
            '반도체': '#667eea',  // LangGraph 메인 색상
            '바이오': '#764ba2',
            '방산': '#f093fb',
            '통신': '#4facfe',
            '원자력': '#43e97b',
            '전력망': '#fa709a',
            '조선': '#fee140',
            'AI': '#FF6B9D',
            '기타': '#30cfd0'
        };
        
        // 데이터 구조 생성
        const labels = [];
        const parents = [];
        const values = [];
        const colors = [];
        
        // 섹터별 그룹화
        const sectorMap = {};
        portfolio.forEach(stock => {
            const sector = stock.sector || '기타';
            if (!sectorMap[sector]) {
                sectorMap[sector] = [];
            }
            sectorMap[sector].push(stock);
        });
        
        console.log('[DEBUG] 섹터 맵:', Object.keys(sectorMap));
        
        // === 3단계 구조: 포트폴리오 → 섹터 → 종목 ===
        
        // 1. 루트 노드 "포트폴리오" 추가
        const totalPortfolioValue = portfolio.reduce((sum, stock) => sum + ((stock.weight || 0) * 100), 0);
        labels.push('포트폴리오');
        parents.push('');  // 최상위 루트
        values.push(totalPortfolioValue);
        colors.push('#FFFFFF');  // 포트폴리오 색상 (흰색)
        
        // 2. 섹터들 추가 (부모: 포트폴리오)
        Object.entries(sectorMap).forEach(([sector, stocks]) => {
            labels.push(sector);
            parents.push('포트폴리오');
            
            const sectorTotal = stocks.reduce((sum, stock) => sum + ((stock.weight || 0) * 100), 0);
            values.push(sectorTotal);
            colors.push(colorMap[sector] || '#30cfd0');
        });
        
        // 3. 종목들 추가 (부모: 각 섹터)
        Object.entries(sectorMap).forEach(([sector, stocks]) => {
            stocks.forEach((stock, idx) => {
                const stockName = stock.name || stock.ticker;
                const stockWeight = (stock.weight || 0) * 100;
                
                labels.push(stockName);
                parents.push(sector);
                values.push(stockWeight);
                
                // 밝은 색상 변형
                const baseColor = colorMap[sector] || '#30cfd0';
                colors.push(baseColor);
            });
        });
        
        // Plotly로 차트 생성
        const chartData = [{
            type: 'sunburst',
            labels: labels,
            parents: parents,
            values: values,
            branchvalues: 'total',  // ⭐ 완전한 원형을 위해 'total' 사용
            marker: {
                colors: colors,
                line: { color: 'white', width: 2 }
            },
            textfont: { size: 12, color: 'black', family: 'Pretendard, Arial, sans-serif' },
            textinfo: 'label',  // 라벨만 표시
            hovertemplate: '<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
            maxdepth: 3,
            rotation: 0,
            sort: false
        }];
        
        const layout = {
            margin: { l: 20, r: 20, t: 20, b: 20 },
            font: { family: 'Pretendard, Arial, sans-serif', size: 12 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            autosize: true,
            width: null,
            height: 280
        };
        
        try {
            // 먼저 기존 차트를 정리
            const chartElement = document.getElementById('sectorChart');
            if (chartElement) {
                chartElement.innerHTML = '';
            }
            
            Plotly.newPlot('sectorChart', chartData, layout, {
                responsive: true,
                displayModeBar: false,
                staticPlot: false
            }).then(() => {
                console.log('✅ createSunburstFromData로 차트 생성 완료');
                // 차트가 생성된 후 리사이즈
                setTimeout(() => {
                    if (window.Plotly && document.getElementById('sectorChart')) {
                        window.Plotly.Plots.resize('sectorChart');
                        console.log('✅ 차트 리사이즈 완료');
                    }
                }, 100);
            }).catch(e => {
                console.error('❌ createSunburstFromData 차트 생성 실패:', e);
                const chartElement = document.getElementById('sectorChart');
                if (chartElement) {
                    chartElement.innerHTML = '<div style="text-align: center; color: #dc3545; padding: 50px;">차트 생성에 실패했습니다</div>';
                }
            });
        } catch (e) {
            console.error('❌ createSunburstFromData 전체 오류:', e);
            const chartElement = document.getElementById('sectorChart');
            if (chartElement) {
                chartElement.innerHTML = '<div style="text-align: center; color: #dc3545; padding: 50px;">차트 라이브러리 오류</div>';
            }
        }
    }        // ⭐ 수익률 차트 전용 함수 - Plotly.js로 변경
        function renderPerformanceChart(data) {
            console.log('[DEBUG] renderPerformanceChart 호출됨');
            console.log('[DEBUG] 전체 data:', data);
            
            const perfContainer = document.getElementById('performanceChart');
            if (!perfContainer) {
                console.error('❌ performanceChart 요소를 찾을 수 없습니다');
                return;
            }
            
            // ⭐ 안전한 데이터 접근
            let perfData = null;
            
            // 방법 1: data.chart_data.expected_performance
            if (data.chart_data && data.chart_data.expected_performance) {
                perfData = data.chart_data.expected_performance;
                console.log('[DEBUG] chart_data.expected_performance 사용');
            }
            // 방법 2: 직접 접근 (months, portfolio, benchmark가 직접 있는 경우)
            else if (data.months && data.portfolio && data.benchmark) {
                perfData = {
                    months: data.months,
                    portfolio: data.portfolio,
                    benchmark: data.benchmark
                };
                console.log('[DEBUG] 직접 데이터 접근 사용');
            }
            
            // 데이터가 없는 경우: 오류 메시지 표시
            if (!perfData) {
                console.warn('⚠️ 수익률 데이터 없음 - 오류 메시지 표시');
                perfContainer.innerHTML = `
                    <div style="
                        display: flex; 
                        flex-direction: column; 
                        align-items: center; 
                        justify-content: center; 
                        height: 100%; 
                        color: #666;
                        text-align: center;
                        padding: 40px;
                    ">
                        <div style="font-size: 48px; margin-bottom: 20px; opacity: 0.3;">📊</div>
                        <h3 style="color: #dc3545; margin-bottom: 10px;">수익률 데이터 생성 실패</h3>
                        <p style="color: #666; line-height: 1.6;">
                            AI 모델에서 수익률 예측 데이터를 생성하지 못했습니다.<br>
                            다른 조건으로 다시 분석해보시거나, 잠시 후 재시도해주세요.
                        </p>
                    </div>
                `;
                return;
            }
            
            console.log('[DEBUG] 사용할 수익률 데이터:', perfData);
            
            // ⭐ Plotly.js를 사용한 수익률 차트 생성
            const trace1 = {
                x: perfData.months.map(m => m + '개월'),
                y: perfData.portfolio,
                type: 'scatter',
                mode: 'lines+markers',
                name: '포트폴리오',
                line: {
                    color: '#667eea',  // LangGraph 색상
                    width: 3,
                    shape: 'spline'
                },
                marker: {
                    color: '#667eea',
                    size: 8,
                    line: {color: 'white', width: 2}
                },
                fill: 'tonexty',
                fillcolor: 'rgba(102, 126, 234, 0.1)'
            };
            
            const trace2 = {
                x: perfData.months.map(m => m + '개월'),
                y: perfData.benchmark,
                type: 'scatter',
                mode: 'lines+markers',
                name: '벤치마크 (KOSPI)',
                line: {
                    color: '#999',
                    width: 2,
                    dash: 'dash',
                    shape: 'spline'
                },
                marker: {
                    color: '#999',
                    size: 6,
                    line: {color: 'white', width: 1}
                },
                fill: 'tozeroy',
                fillcolor: 'rgba(153, 153, 153, 0.05)'
            };
            
            const layout = {
                title: {
                    text: '',
                    font: {size: 16, family: 'Pretendard, Arial, sans-serif'}
                },
                xaxis: {
                    title: '투자 기간',
                    showgrid: true,
                    gridcolor: '#f0f0f0'
                },
                yaxis: {
                    title: '수익률 (%)',
                    showgrid: true,
                    gridcolor: '#f0f0f0',
                    ticksuffix: '%'
                },
                legend: {
                    x: 0,
                    y: 1,
                    bgcolor: 'rgba(255,255,255,0.8)',
                    bordercolor: '#ddd',
                    borderwidth: 1
                },
                margin: {l: 60, r: 40, t: 40, b: 60},
                plot_bgcolor: 'white',
                paper_bgcolor: 'white',
                hovermode: 'x unified',
                font: {family: 'Pretendard, Arial, sans-serif'}
            };
            
            const config = {
                responsive: true,
                displayModeBar: false
            };
            
            Plotly.newPlot(perfContainer, [trace1, trace2], layout, config);
        }
        
        // ⭐ PDF 내보내기 함수
        async function exportToPDF() {
            try {
                console.log('📄 PDF 내보내기 시작...');
                
                // 현재 결과 HTML을 가져와서 PDF용으로 정리
                const resultElement = document.getElementById('resultContent');
                if (!resultElement) {
                    alert('내보낼 결과가 없습니다.');
                    return;
                }
                
                // PDF용 HTML 생성
                const pdfHtml = `
                    <!DOCTYPE html>
                    <html lang="ko">
                    <head>
                        <meta charset="UTF-8">
                        <title>AI 포트폴리오 분석 보고서 - LangGraph</title>
                        <style>
                            body { font-family: 'Pretendard', Arial, sans-serif; margin: 20px; font-size: 14px; }
                            .header { text-align: center; margin-bottom: 30px; }
                            .section { margin-bottom: 25px; page-break-inside: avoid; }
                            .section-title { color: #667eea; font-size: 22px; font-weight: 600; margin-bottom: 15px; border-bottom: 2px solid #667eea; padding-bottom: 5px; }
                            .summary-box { background: #f8f9ff; border-left: 4px solid #667eea; padding: 15px; border-radius: 8px; line-height: 1.6; }
                            .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 15px 0; }
                            .metric-card { background: white; border: 2px solid #e9ecef; border-radius: 8px; padding: 15px; text-align: center; }
                            .metric-label { font-size: 14px; color: #666; margin-bottom: 5px; }
                            .metric-value { font-size: 24px; font-weight: 700; color: #667eea; }
                            .stock-table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 14px; }
                            .stock-table th { background: #f8f9fa; padding: 8px; border: 1px solid #ddd; font-weight: 600; }
                            .stock-table td { padding: 8px; border: 1px solid #ddd; }
                            .badge-sector { background: #f0e7ff; color: #667eea; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
                            .btn-primary, #downloadPdfBtn, button, input[type='submit'] { display: none !important; }
                            /* PDF에서 차트 크기 조정 및 같은 페이지 배치 */
                            .plotly-graph-div { max-height: 280px !important; page-break-inside: avoid; }
                            #sectorChart, #performanceChart { max-height: 280px !important; page-break-inside: avoid; margin: 10px 0; }
                            .charts-container { page-break-inside: avoid; display: flex; justify-content: space-between; gap: 20px; margin: 20px 0; }
                            .chart-wrapper { flex: 1; max-height: 280px; }
                        </style>
                    </head>
                    <body>
                        <div class="header">
                            <h1>🤖 AI 투자 포트폴리오 분석 보고서</h1>
                            <p style="color: #667eea; font-weight: 600;">⚡ LangGraph 기반 분석 결과</p>
                            <p style="color: #999; font-size: 14px;">생성일시: ` + new Date().toLocaleString('ko-KR') + `</p>
                        </div>
                        ` + resultElement.innerHTML + `
                    </body>
                    </html>
                `;
                
                // PDF 생성 요청
                const response = await fetch('/api/export-pdf', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ html_content: pdfHtml })
                });
                
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `portfolio_analysis_langgraph_${new Date().getTime()}.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                    
                    console.log('✅ PDF 다운로드 완료');
                } else {
                    throw new Error('PDF 생성 실패');
                }
                
            } catch (error) {
                console.error('❌ PDF 내보내기 오류:', error);
                alert('PDF 내보내기 중 오류가 발생했습니다: ' + error.message);
            }
        }
        
        loadSectors();
        loadStocks();
        
        // ⭐ 예산 포맷팅 함수 (만원 단위까지)
        function formatBudget(num) {
            num = parseInt(num) || 0;
            
            if (num >= 100000000) {
                const eok = Math.floor(num / 100000000);
                const remainder = num % 100000000;
                const cheonman = Math.floor(remainder / 10000000);
                
                if (cheonman > 0) {
                    return `${eok}억 ${cheonman}천만원`;
                }
                return `${eok}억원`;
            } 
            else if (num >= 10000000) {
                const cheonman = Math.floor(num / 10000000);
                const baekman = Math.floor((num % 10000000) / 1000000);
                
                if (baekman > 0) {
                    return `${cheonman}천 ${baekman}백만원`;
                }
                return `${cheonman}천만원`;
            } 
            else if (num >= 1000000) {
                const baekman = Math.floor(num / 1000000);
                return `${baekman}백만원`;
            }
            else if (num >= 10000) {
                const man = Math.floor(num / 10000);
                return `${man}만원`;
            }
            
            return num.toLocaleString() + '원';
        }
        
        const budgetInput = document.getElementById('budgetInput');
        const budgetDisplay = document.getElementById('budgetDisplay');
        
        if (budgetInput && budgetDisplay) {
            // 입력할 때마다 오른쪽 디스플레이 업데이트
            budgetInput.addEventListener('input', function() {
                budgetDisplay.textContent = formatBudget(this.value);
            });
            
            // 초기값 표시
            budgetDisplay.textContent = formatBudget(budgetInput.value);
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 LangGraph 포트폴리오 분석 시스템 시작")
    print("="*60)
    print("📍 http://localhost:8001 에서 확인하세요")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)