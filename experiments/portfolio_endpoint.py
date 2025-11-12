"""
main.py

Portfolio Analysis System v2 - 고도화된 입출력 구조
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import plotly.graph_objects as go
from plotly.io import to_html
import json
# import pdfkit  # ⭐ 제거됨
from playwright.sync_api import sync_playwright
import io
from datetime import datetime

from agent_test.portfolio_agent_anthropic import run_portfolio_agent, AVAILABLE_STOCKS, SECTORS
from core.llm_clients import AVAILABLE_MODELS

app = FastAPI(title="AI 투자 포트폴리오 분석 시스템 v2")


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
    model_name: Literal["solar-pro", "gpt-4o-mini", "gpt-4o"] = Field(default="gpt-4o-mini", description="분석 엔진")
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
    """사용 가능한 AI 모델 리스트"""
    return {
        "models": AVAILABLE_MODELS,
        "default_model": AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "No Models Available"
    }

@app.post("/api/analyze")
async def analyze_portfolio(request: PortfolioRequest):
    """포트폴리오 분석 실행"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 분석 요청:")
        print(f"  예산: {request.budget:,}원")
        print(f"  섹터: {request.investment_targets.sectors}")
        print(f"  종목: {request.investment_targets.tickers}")
        print(f"  성향: {request.risk_profile}")
        print(f"  기간: {request.investment_period}")
        print(f"  모델: {request.model_name}")
        print(f"{'='*60}\n")
        
        result = run_portfolio_agent(
            budget=request.budget,
            investment_targets={
                "sectors": request.investment_targets.sectors,
                "tickers": request.investment_targets.tickers
            },
            risk_profile=request.risk_profile,
            investment_period=request.investment_period,
            model_name=request.model_name,
            additional_prompt=request.additional_prompt
        )
        
        if result["success"]:
            # ⭐ JSON 파싱 (개선된 버전)
            import re
            report_text = result.get("final_report", "")
            
            print(f"\n[DEBUG] report_text 길이: {len(report_text)}")
            print(f"[DEBUG] report_text 처음 200글자: {report_text[:200]}\n")
            
            data = None
            
            # 1단계: ```json 블록 찾기
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', report_text)
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    data = json.loads(json_str)
                    print("✅ JSON 블록에서 파싱 성공")
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON 블록 파싱 실패: {e}")
            
            # 2단계: 직접 JSON 파싱 시도
            if not data:
                try:
                    data = json.loads(report_text)
                    print("✅ 직접 JSON 파싱 성공")
                except json.JSONDecodeError as e:
                    print(f"⚠️ 직접 JSON 파싱 실패: {e}")
            
            # 3단계: 실패한 경우 기본값 사용
            if not data:
                print("❌ JSON 파싱 완전 실패 - 기본값 사용")
                data = {
                    "ai_summary": "분석 결과를 불러올 수 없습니다.",
                    "portfolio_allocation": [],
                    "performance_metrics": {},
                    "chart_data": {}
                }
            
            # ⭐ Sunburst 차트 생성
            sunburst_chart, chart_config = create_sunburst_chart(data)
            
            # 차트를 HTML로 변환 (⭐ 수정)
            chart_html = to_html(
                sunburst_chart, 
                include_plotlyjs='cdn',
                full_html=False,  # ⭐ False로 설정
                div_id="sectorChart"
            )
            
            print(f"[DEBUG] chart_html 생성됨, 길이: {len(chart_html)}")
            print(f"[DEBUG] chart_html 샘플:\n{chart_html[:300]}\n")
            
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
            
            # 데이터에 차트 HTML과 설정 추가
            data['chart_html'] = chart_html
            data['chart_config'] = chart_config
            data['chart_data'] = chart_data  # ⭐ 추가
            
            return JSONResponse(content={
                "success": True,
                "report": json.dumps(data, ensure_ascii=False),
                "iterations": result.get("iterations", 1)
            })
        else:
            print(f"❌ 분석 실패: {result}")
            raise HTTPException(status_code=500, detail=result.get("error", "알 수 없는 오류"))
    
    except Exception as e:
        import traceback
        print(f"\n❌ 서버 오류:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


def create_sunburst_chart(data):
    """3단계 구조의 완전한 원형 Sunburst 차트 생성"""
    
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
    
    # 색상 매핑
    colorMap = {
        '반도체': '#4A5FC1',
        '바이오': '#5C3D7C',
        '방산': '#C94E8C',
        '통신': '#2A7FBA',
        '원자력': '#2D8F5C',
        '전력망': '#D63D5C',
        '조선': '#DAA520',
        'AI': '#FF6B9D',
        '기타': '#1B8B8B'
    }
    
    def lighten_color(hex_color, brightness_level=0):
        """밝기 조정 함수"""
        if hex_color.startswith('rgb'):
            return hex_color
            
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        
        factor = 1 + (brightness_level * 0.15)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        
        return f"rgb({r},{g},{b})"
    
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
        labels.append(sector)
        parents.append('포트폴리오')  # 부모는 포트폴리오
        
        # 섹터의 총 비중 계산
        sector_total = sum((stock.get('weight', 0) * 100) for stock in stocks)
        values.append(sector_total)
        colors.append(colorMap.get(sector, '#1B8B8B'))
        
        print(f"섹터 {sector}: {sector_total:.1f}%")
    
    # 3. 종목들 추가 (부모: 각 섹터)
    sector_stock_index = {}
    for sector, stocks in sector_map.items():
        if sector not in sector_stock_index:
            sector_stock_index[sector] = 0
        
        for stock in stocks:
            stock_name = stock.get('name') or stock.get('ticker', '미정')
            stock_weight = (stock.get('weight', 0) * 100)
            
            labels.append(stock_name)
            parents.append(sector)  # 부모는 섹터
            values.append(stock_weight)
            
            # 밝은 색상 적용
            brightness = sector_stock_index[sector]
            sector_stock_index[sector] += 1
            base_color = colorMap.get(sector, '#1B8B8B')
            lighter_color = lighten_color(base_color, brightness)
            colors.append(lighter_color)
            
            print(f"  종목 {stock_name}: {stock_weight:.1f}% ({lighter_color})")
    
    print(f"[DEBUG] 차트 labels: {labels}")
    print(f"[DEBUG] 차트 values: {values}")
    
    # go.Sunburst로 차트 생성
    fig_sunburst = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues='total',  # 🔥 완전한 원형을 위해 'total' 사용
        marker=dict(
            colors=colors,
            line=dict(color='white', width=2)
        ),
        textfont=dict(size=12, color='white', family='Pretendard, Arial, sans-serif'),
        textinfo='label',  # 🔥 라벨만 표시
        hovertemplate='<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
        maxdepth=3,  # 3단계 모두 표시
        rotation=0,   # 회전 고정
        sort=False    # 정렬 비활성화
    ))
    
    # 레이아웃 설정
    fig_sunburst.update_layout(
        font=dict(
            family="Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Arial, sans-serif",
            size=16,
            color='white'
        ),
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        autosize=True,
        width=None,
        height=350  # PDF 호환성을 위해 크기 축소
    )
    
    # 차트 설정을 JSON으로도 반환
    chart_config = {
        'labels': labels,
        'parents': parents,
        'values': values,
        'colors': colors,
        'layout': {
            'font': {'family': 'Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif', 'size': 14},
            'margin': {'l': 20, 'r': 20, 't': 20, 'b': 20},
            'paper_bgcolor': 'rgba(0,0,0,0)',
            'plot_bgcolor': 'rgba(0,0,0,0)',
            'autosize': True,
            'width': None,
            'height': 350  # PDF 호환성을 위해 크기 축소
        }
    }
    
    return fig_sunburst, chart_config


# =====================================================
# HTML UI
# =====================================================

HTML_UI = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 투자 포트폴리오 분석 v2</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>  <!-- ✅ 이미 있음 -->
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            color: #667eea;
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
            border-color: #667eea;
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
            background: #667eea;
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
            color: #667eea;
            margin-top: 10px;
            font-weight: 600;
        }
        
        .btn-primary {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
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
            border-top: 5px solid #667eea;
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
        
        /* 결과 화면 스타일 */
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
            color: #667eea;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .summary-box {
            background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
            border-left: 4px solid #667eea;
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
            border-color: #667eea;
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
            color: #667eea;
        }
        
        .metric-unit {
            font-size: 0.5em;
            color: #999;
        }
        
        .chart-container {
            position: relative;
            height: 380px;  /* PDF와 일치하도록 축소 */
            margin: 20px 0;
            overflow: hidden;
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

        /* 데이터 분석 점수 칸 특별 처리 */
        .stock-table td:nth-child(2) .score-bar {
            max-width: 80px;  /* ← 더 작게 */
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
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
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
            background: #e7f3ff;
            color: #0066cc;
        }
        
        /* AI 엔진 선택 스타일 */
        .ai-engine-option {
            position: relative;
        }
        
        .ai-engine-option input[type="radio"] {
            display: none;
        }
        
        .engine-label {
            display: block;
            padding: 15px;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
            background: white;
        }
        
        .engine-label:hover {
            border-color: #667eea;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
        }
        
        .ai-engine-option input[type="radio"]:checked + .engine-label {
            border-color: #667eea;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .engine-title {
            font-weight: 700;
            font-size: 1.1em;
            margin-bottom: 5px;
        }
        
        .engine-desc {
            font-size: 0.9em;
            opacity: 0.8;
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
            <p>고도화된 데이터 기반 투자 전략 분석</p>
        </div>
        
        <div class="main-content">
            <!-- 입력 패널 -->
            <div class="panel input-panel">
                <h2>📝 투자 조건 입력</h2>
                
                <form id="portfolioForm">
                    <!-- 0. AI 엔진 및 모델 선택 -->
                    <div class="form-group">
                        <label>🤖 AI 분석 엔진</label>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                            <div class="ai-engine-option">
                                <input type="radio" id="anthropic" name="aiEngine" value="anthropic" checked>
                                <label for="anthropic" class="engine-label">
                                    <div class="engine-title">🌟 Anthropic</div>
                                    <div class="engine-desc">빠르고 안정적인 분석</div>
                                </label>
                            </div>
                            <div class="ai-engine-option">
                                <input type="radio" id="langgraph" name="aiEngine" value="langgraph">
                                <label for="langgraph" class="engine-label">
                                    <div class="engine-title">⚡ LangGraph</div>
                                    <div class="engine-desc">고급 그래프 기반 분석</div>
                                </label>
                            </div>
                        </div>
                        
                        <!-- 모델 선택 -->
                        <label>🎯 분석 모델</label>
                        <select id="modelSelect" name="model" style="width: 100%; padding: 12px; border-radius: 8px; border: 2px solid #e9ecef; font-size: 1em;">
                            <option value="">모델을 로딩 중...</option>
                        </select>
                    </div>
                    
                    <!-- 1. 투자 예산 -->
                    <div class="form-group">
                        <label>💰 총 투자 예산 (원)</label>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <input type="number" id="budgetInput" name="budget" value="5000000" 
                                   min="1000000" step="10000" required
                                   style="flex: 1; font-size: 1.05em; text-align: right;">
                            <span id="budgetDisplay" style="min-width: 140px; font-weight: 600; color: #667eea; text-align: right; padding: 12px 15px; background: #f8f9fa; border-radius: 8px; border: 2px solid #e9ecef; font-size: 1.1em; white-space: nowrap;">
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
                    <p>AI가 최적의 포트폴리오를 분석합니다</p>
                </div>
                
                <div id="loadingState" class="loading" style="display: none;">
                    <div class="spinner"></div>
                    <h3>AI가 포트폴리오를 분석하고 있습니다...</h3>
                    <p style="margin-top: 10px; color: #666;">
                        데이터 수집 → 점수 계산 → 최적화 → 보고서 생성
                    </p>
                </div>
                
                <div id="resultContent" class="result-content"></div>
            </div>
        </div>
    </div>
    
    <script>
        // 탭 전환
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                tab.classList.add('active');
                document.getElementById(`${tabName}-tab`).classList.add('active');
            });
        });
        
        // 섹터 리스트 로드
        async function loadSectors() {
            try {
                console.log('[LOADING] 섹터 목록 로드 중...');
                const response = await fetch('/api/sectors');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('✅ 섹터 데이터 수신:', data);
                
                const sectorsList = document.getElementById('sectorsList');
                if (!sectorsList) {
                    throw new Error('sectorsList 요소를 찾을 수 없습니다');
                }
                
                sectorsList.innerHTML = data.sectors.map(sector => `
                    <div class="selection-item">
                        <input type="checkbox" id="sector_` + sector + `" name="sectors" value="` + sector + `" onchange="updateCount('sectors')">
                        <label for="sector_` + sector + `">` + sector + `</label>
                    </div>
                `).join('');
                
                console.log(`✅ 섹터 ${data.sectors.length}개 로드 완료`);
            } catch (error) {
                console.error('❌ 섹터 로드 실패:', error);
                const sectorsList = document.getElementById('sectorsList');
                if (sectorsList) {
                    sectorsList.innerHTML = '<p style="color: red;">섹터 로드 실패: ' + error.message + '</p>';
                }
            }
        }
        
        // 종목 리스트 로드
        async function loadStocks() {
            try {
                console.log('[LOADING] 종목 목록 로드 중...');
                const response = await fetch('/api/stocks');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('✅ 종목 데이터 수신:', data);
                
                const stocksList = document.getElementById('stocksList');
                if (!stocksList) {
                    throw new Error('stocksList 요소를 찾을 수 없습니다');
                }
                
                stocksList.innerHTML = data.stocks.map(stock => `
                    <div class="selection-item">
                        <input type="checkbox" id="stock_` + stock.ticker + `" name="stocks" value="` + stock.ticker + `" onchange="updateCount('stocks')">
                        <label for="stock_` + stock.ticker + `">` + stock.name + `</label>
                    </div>
                `).join('');
                
                console.log(`✅ 종목 ${data.stocks.length}개 로드 완료`);
            } catch (error) {
                console.error('❌ 종목 로드 실패:', error);
                const stocksList = document.getElementById('stocksList');
                if (stocksList) {
                    stocksList.innerHTML = '<p style="color: red;">종목 로드 실패: ' + error.message + '</p>';
                }
            }
        }
        
        // 사용 가능한 모델 목록 로드
        async function loadAvailableModels() {
            try {
                console.log('🔄 사용 가능한 모델 목록 로딩...');
                const response = await fetch('/api/models');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('✅ 모델 데이터 수신:', data);
                
                return data.models;
            } catch (error) {
                console.error('❌ 모델 로드 실패:', error);
                return ['claude-3-5-sonnet-20241022']; // 기본 fallback
            }
        }
        
        // AI 엔진 변경 시 모델 옵션 업데이트
        async function updateModelOptions() {
            const selectedEngine = document.querySelector('input[name="aiEngine"]:checked').value;
            const modelSelect = document.getElementById('modelSelect');
            
            // 로딩 표시
            modelSelect.innerHTML = '<option value="">모델 로딩 중...</option>';
            
            try {
                const availableModels = await loadAvailableModels();
                
                if (selectedEngine === 'langgraph') {
                    // LangGraph는 모든 사용 가능한 모델 + 추가 모델
                    const langGraphModels = [
                        ...availableModels,
                        'gpt-4o',
                        'gpt-4o-mini'
                    ];
                    
                    modelSelect.innerHTML = [...new Set(langGraphModels)].map(model => 
                        `<option value="${model}">${getModelDisplayName(model)}</option>`
                    ).join('');
                } else {
                    // Anthropic는 사용 가능한 모델만
                    modelSelect.innerHTML = availableModels.map(model => 
                        `<option value="${model}">${getModelDisplayName(model)}</option>`
                    ).join('');
                }
                
                console.log(`✅ ${selectedEngine} 엔진용 모델 목록 업데이트 완료`);
            } catch (error) {
                console.error('❌ 모델 목록 업데이트 실패:', error);
                modelSelect.innerHTML = '<option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet (기본)</option>';
            }
        }
        
        // 모델 이름을 사용자 친화적으로 변환
        function getModelDisplayName(modelName) {
            const displayNames = {
                'claude-3-5-sonnet-20241022': 'Claude 3.5 Sonnet (최신)',
                'claude-3-sonnet-20240229': 'Claude 3 Sonnet',
                'claude-3-haiku-20240307': 'Claude 3 Haiku (빠름)',
                'gpt-4o': 'GPT-4O (OpenAI)',
                'gpt-4o-mini': 'GPT-4O Mini (OpenAI)',
                'solar-pro2': 'Solar Pro 2 (Upstage)'
            };
            return displayNames[modelName] || modelName;
        }
        
        // 엔진 선택 이벤트 리스너 추가
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('input[name="aiEngine"]').forEach(radio => {
                radio.addEventListener('change', updateModelOptions);
            });
            
            // 초기 모델 목록 로드
            updateModelOptions();
        });
        
        // 선택 개수 업데이트
        function updateCount(type) {
            const count = document.querySelectorAll(`input[name="${type}"]:checked`).length;
            document.getElementById(`${type}Count`).textContent = `선택: ${count}개`;
        }
        
        // ⭐ DOM이 완전히 로드된 후 초기 함수 실행
        document.addEventListener('DOMContentLoaded', function() {
            console.log('[OK] DOM 로드 완료 - 초기 함수 실행');
            loadSectors();
            loadStocks();
            updateModelOptions(); // 초기 모델 목록 로드
            
            // 예산 input 초기화
            const budgetInput = document.getElementById('budgetInput');
            const budgetDisplay = document.getElementById('budgetDisplay');
            
            if (budgetInput && budgetDisplay) {
                budgetDisplay.textContent = formatBudget(budgetInput.value);
                
                budgetInput.addEventListener('input', function() {
                    budgetDisplay.textContent = formatBudget(this.value);
                });
            }
        });
        
        // ⭐ 예산 포맷팅 함수
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
        
        // 폼 제출
        document.getElementById('portfolioForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const selectedSectors = Array.from(document.querySelectorAll('input[name="sectors"]:checked')).map(cb => cb.value);
            const selectedStocks = Array.from(document.querySelectorAll('input[name="stocks"]:checked')).map(cb => cb.value);
            const selectedEngine = formData.get('aiEngine');
            const selectedModel = formData.get('model');
            
            if (selectedSectors.length === 0 && selectedStocks.length === 0) {
                alert('섹터 또는 종목을 최소 1개 이상 선택해주세요.');
                return;
            }

            // 엔드포인트 결정
            const apiEndpoint = selectedEngine === 'langgraph' ? 'http://localhost:8001/api/analyze' : '/api/analyze';
            
            const requestData = {
                budget: parseInt(formData.get('budget')),
                investment_targets: {
                    sectors: selectedSectors,
                    tickers: selectedStocks
                },
                risk_profile: formData.get('risk_profile'),
                investment_period: formData.get('investment_period'),
                model_name: selectedModel,
                additional_prompt: formData.get('additional_prompt') || ""
            };
            
            // UI 상태 변경
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('loadingState').style.display = 'flex';
            document.getElementById('resultContent').classList.remove('active');
            document.getElementById('analyzeBtn').disabled = true;
            
            // 선택된 엔진 표시
            const engineDisplay = selectedEngine === 'langgraph' ? '⚡ LangGraph' : '� Anthropic Claude';
            const loadingText = document.querySelector('#loadingState p');
            if (loadingText) {
                loadingText.innerHTML = `${engineDisplay} 엔진으로 포트폴리오를 분석하고 있습니다...<br><small>선택된 모델: ${selectedModel}</small>`;
            }

            try {
                console.log(`🚀 ${engineDisplay} 엔진으로 요청 전송:`, apiEndpoint);
                const response = await fetch(apiEndpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    renderResults(result.report, result.iterations);
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
        
        // 결과 렌더링 함수
        function renderResults(reportText, iterations) {
            let data = null;
            
            try {
                // ⭐ 정규식을 변수로 분리하여 안전하게 처리
                const jsonStart = reportText.indexOf('```json');
                const jsonEnd = reportText.indexOf('```', jsonStart + 7);
                
                if (jsonStart !== -1 && jsonEnd !== -1) {
                    const jsonStr = reportText.substring(jsonStart + 7, jsonEnd).trim();
                    data = JSON.parse(jsonStr);
                } else {
                    data = JSON.parse(reportText);
                }
            } catch (e) {
                document.getElementById('resultContent').innerHTML = `
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 12px;">
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">${reportText}</pre>
                    </div>
                `;
                document.getElementById('resultContent').classList.add('active');
                return;
            }
            
            // 구조화된 결과 렌더링
            let html = `
                <div style="color: #28a745; margin-bottom: 25px; font-weight: 600; font-size: 1.05em;">
                    ✅ 분석 완료 (` + iterations + `회 반복)
                </div>
                
                <!-- 1. AI 종합 요약 -->
                <div class="section">
                    <div class="section-title">🎯 AI 종합 브리핑</div>
                    <div class="summary-box">` + (data.ai_summary || '분석 요약 정보 없음') + `</div>
                </div>
                
                <!-- 2. 성과 지표 -->
                <div class="section">
                    <div class="section-title">📈 예상 성과 지표</div>
                    <div class="metrics-grid">
            `;
            
            if (data.performance_metrics) {
                const pm = data.performance_metrics;
                html += `
                    <div class="metric-card">
                        <div class="metric-label">예상 수익률</div>
                        <div class="metric-value">` + (pm.expected_return || 0) + `<span class="metric-unit">%</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">최대 낙폭 (MDD)</div>
                        <div class="metric-value" style="color: #dc3545;">` + (pm.max_drawdown || 0) + `<span class="metric-unit">%</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">샤프 비율</div>
                        <div class="metric-value">` + (pm.sharpe_ratio || 0) + `</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">벤치마크 초과수익</div>
                        <div class="metric-value">` + (pm.benchmark_alpha || 0) + `<span class="metric-unit">%p</span></div>
                    </div>
                `;
            }
            
            html += `
                    </div>
                </div>
                
                <!-- 3. 추천 종목 종합표 -->
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
            
            if (data.portfolio_allocation) {
                data.portfolio_allocation.forEach(stock => {
                    const avgScore = stock.scores ? 
                        Math.round((stock.scores.data_analysis + stock.scores.financial + stock.scores.news) / 3) : 0;
                    
                    html += `
                        <tr>
                            <td><strong>` + (stock.name || stock.ticker) + `</strong></td>
                            <td><span class="badge badge-sector">` + stock.sector + `</span></td>
                            <td><strong>` + (stock.weight * 100).toFixed(1) + `%</strong></td>
                            <td>` + (stock.amount || 0).toLocaleString() + `원</td>
                            <td>` + (stock.shares || 0) + `주</td>
                            <td>` + (stock.current_price || 0).toLocaleString() + `원</td>
                            <td style="color: #28a745; font-weight: 600;">` + (stock.target_price || 0).toLocaleString() + `원</td>
                            <td style="color: #dc3545; font-weight: 600;">` + (stock.stop_loss || 0).toLocaleString() + `원</td>
                            <td>
                                <div style="font-weight: 600; margin-bottom: 5px;">` + avgScore + `점</div>
                                <div class="score-bar">
                                    <div class="score-fill" style="width: ` + avgScore + `%"></div>
                                </div>
                            </td>
                        </tr>
                    `;
                });
            }
            
            html += `
                        </tbody>
                    </table>
                </div>
                
                <!-- 4. 점수 상세 -->
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
            
            if (data.portfolio_allocation) {
                data.portfolio_allocation.forEach(stock => {
                    if (stock.scores) {
                        const avgScore = Math.round((stock.scores.data_analysis + stock.scores.financial + stock.scores.news) / 3);
                        html += `
                            <tr>
                                <td><strong>` + stock.name + ` <span style="color: #999; font-weight: normal; font-size: 0.9em;">(` + stock.ticker + `)</span></strong></td>
                                <td>
                                    <div>` + stock.scores.data_analysis + `점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ` + stock.scores.data_analysis + `%"></div>
                                    </div>
                                </td>
                                <td>
                                    <div>` + stock.scores.financial + `점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ` + stock.scores.financial + `%"></div>
                                    </div>
                                </td>
                                <td>
                                    <div>` + stock.scores.news + `점</div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width: ` + stock.scores.news + `%"></div>
                                    </div>
                                </td>
                                <td><strong style="color: #667eea; font-size: 1.1em;">` + avgScore + `점</strong></td>
                            </tr>
                        `;
                    }
                });
            }
            
            html += `
                        </tbody>
                    </table>
                </div>
                
                <!-- 5. 섹터 비중 차트 -->
                <div class="section">
                    <div class="section-title">🌞 포트폴리오 구성 (포트폴리오 → 섹터 → 종목)</div>
                    <div class="chart-container" id="chartContainer">
                        <div id="sectorChart" style="height: 350px; width: 100%;"></div>
                    </div>
                </div>
                
                <!-- 6. 예상 수익률 차트 -->
                <div class="section">
                    <div class="section-title">📊 예상 수익률 추이 (벤치마크 비교)</div>
                    <div class="chart-container">
                        <div id="performanceChart" style="height: 350px; width: 100%;"></div>
                    </div>
                </div>
            `;
            
            document.getElementById('resultContent').innerHTML = html;
            document.getElementById('resultContent').classList.add('active');
            
            // ⭐ PDF 다운로드 버튼을 맨 위에 추가
            const pdfBtnHtml = `
                <button id="downloadPdfBtn" class="btn-primary" style="margin-bottom: 20px; background: linear-gradient(135deg, #28a745 0%, #20c997 100%);">
                    PDF 다운로드
                </button>
            `;
            document.getElementById('resultContent').insertAdjacentHTML('afterbegin', pdfBtnHtml);
            
            // PDF 다운로드 이벤트 (클론으로 중복 방지)
            const downloadBtn = document.getElementById('downloadPdfBtn');
            const newBtn = downloadBtn.cloneNode(true);
            downloadBtn.parentNode.replaceChild(newBtn, downloadBtn);
            
            newBtn.addEventListener('click', async () => {
                newBtn.disabled = true;
                newBtn.textContent = 'PDF 생성 중...';
                
                try {
                    const resultHtml = document.getElementById('resultContent').innerHTML;
                    
                    const fullHtml = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <style>
                                * { margin: 0; padding: 0; box-sizing: border-box; }
                                body { 
                                    font-family: 'Pretendard', sans-serif; 
                                    padding: 20px;
                                    font-size: 14px;
                                }
                                .section { margin-bottom: 30px; page-break-inside: avoid; }
                                .section-title { 
                                    font-size: 22px; 
                                    color: #667eea; 
                                    margin-bottom: 15px; 
                                    padding-bottom: 10px; 
                                    border-bottom: 2px solid #667eea; 
                                }
                                .summary-box {
                                    background: #f8f9fa;
                                    border-left: 4px solid #667eea;
                                    padding: 15px;
                                    margin: 10px 0;
                                    line-height: 1.6;
                                }
                                .metrics-grid { 
                                    display: grid; 
                                    grid-template-columns: repeat(4, 1fr); 
                                    gap: 15px; 
                                    margin: 20px 0; 
                                }
                                .metric-card {
                                    border: 2px solid #e9ecef;
                                    padding: 15px;
                                    text-align: center;
                                    border-radius: 8px;
                                }
                                .metric-label { font-size: 12px; color: #666; margin-bottom: 8px; }
                                .metric-value { font-size: 28px; font-weight: bold; color: #667eea; }
                                .metric-unit { font-size: 14px; color: #999; }
                                .stock-table {
                                    width: 100%;
                                    border-collapse: collapse;
                                    margin: 20px 0;
                                }
                                .stock-table th {
                                    background: #f8f9fa;
                                    padding: 10px;
                                    text-align: left;
                                    border-bottom: 2px solid #dee2e6;
                                    font-size: 10px;
                                }
                                .stock-table td {
                                    padding: 8px;
                                    border-bottom: 1px solid #e9ecef;
                                    font-size: 9px;
                                }
                                .score-bar {
                                    width: 60px;
                                    height: 6px;
                                    background: #e9ecef;
                                    border-radius: 3px;
                                    overflow: hidden;
                                    margin-top: 3px;
                                }
                                .score-fill {
                                    height: 100%;
                                    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                                }
                                .badge {
                                    display: inline-block;
                                    padding: 3px 8px;
                                    border-radius: 4px;
                                    font-size: 9px;
                                    font-weight: 600;
                                }
                                .badge-sector { background: #e7f3ff; color: #0066cc; }
                                h1 { 
                                    color: #667eea; 
                                    text-align: center; 
                                    margin-bottom: 30px;
                                    font-size: 28px;
                                }
                                .btn-primary { display: none !important; }
                                #downloadPdfBtn { display: none !important; }
                                /* 차트는 이제 표시됩니다! */
                            </style>
                        </head>
                        <body>
                            <h1>🤖 AI 투자 포트폴리오 분석 보고서</h1>
                            <p style="text-align: center; color: #666; margin-bottom: 40px;">
                                생성일시: ${new Date().toLocaleString('ko-KR')}
                            </p>
                            ${resultHtml}
                        </body>
                        </html>
                    `;
                    
                    const response = await fetch('/api/download-pdf', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ html: fullHtml })
                    });
                    
                    if (!response.ok) throw new Error('PDF 생성 실패');
                    
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `portfolio_analysis_${new Date().getTime()}.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                    
                    newBtn.textContent = 'PDF 다운로드';
                    newBtn.disabled = false;
                } catch (error) {
                    alert('PDF 다운로드 실패: ' + error.message);
                    newBtn.textContent = 'PDF 다운로드';
                    newBtn.disabled = false;
                }
            });
            
            console.log('[DEBUG] 차트 데이터:', data);
            console.log('[DEBUG] chart_config 존재 여부:', !!data.chart_config);
            
            // ⭐ DOM이 완전히 렌더링된 후 차트 삽입
            setTimeout(() => {
                console.log('=== 차트 렌더링 시작 ===');
                
                // ⭐ 방법 1: chart_config로 안전하게 렌더링 (우선)
                if (data.chart_config) {
                    console.log('[DEBUG] chart_config 사용하여 차트 생성');
                    renderSunburstFromConfig(data.chart_config);
                    
                // ⭐ 방법 2: chart_html 백업 (기존 방식)
                } else if (data.chart_html) {
                    console.log('[DEBUG] chart_html 백업 방식 사용');
                    const sectorChart = document.getElementById('sectorChart');
                    if (sectorChart) {
                        // iframe으로 안전하게 삽입
                        const escapedHtml = data.chart_html.replace(/"/g, '&quot;');
                        sectorChart.innerHTML = `<iframe srcdoc="` + escapedHtml + `" style="width:100%; height:430px; border:none;"></iframe>`;
                    }
                    
                // ⭐ 방법 3: 포트폴리오 데이터로 직접 생성 (최후의 수단)
                } else {
                    console.log('[DEBUG] 포트폴리오 데이터로 직접 차트 생성');
                    createSunburstFromData(data.portfolio_allocation);
                }
                
                console.log('=== 차트 렌더링 종료 ===');
                
                // 수익률 차트 렌더링
                setTimeout(() => {
                    renderPerformanceChart(data);
                }, 100);
            }, 300);
        }
        
        // ⭐ renderResults 함수 끝
        function renderSunburstFromConfig(config) {
            console.log('[renderSunburstFromConfig] 함수 호출됨');
            console.log('[DEBUG] config:', config);
            
            try {
                const chartData = [{
                    type: 'sunburst',
                    labels: config.labels,
                    parents: config.parents,
                    values: config.values,
                    branchvalues: 'total',  // 🔥 완전한 원형을 위해 'total' 사용
                    marker: {
                        colors: config.colors,
                        line: { color: 'white', width: 2 }
                    },
                    textfont: { size: 12, color: 'white', family: 'Pretendard, Arial, sans-serif' },
                    textinfo: 'label',  // 🔥 라벨만 표시
                    hovertemplate: '<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
                    maxdepth: 3,  // 🔥 3단계 구조 지원
                    rotation: 0,  // 회전 각도 고정
                    sort: false   // 정렬 비활성화로 완전한 원 유지
                }];
                
                const layout = config.layout || {
                    margin: { l: 20, r: 20, t: 20, b: 20 },
                    font: { family: 'Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif', size: 14 },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)',
                    autosize: true,
                    width: null,
                    height: 350  // PDF 호환성을 위해 크기 축소
                };
                
                Plotly.newPlot('sectorChart', chartData, layout, {
                    responsive: true,
                    displayModeBar: false,
                    staticPlot: false
                });
                
                console.log('[OK] Plotly.newPlot으로 3단계 차트 생성 완료');
                
            } catch (e) {
                console.error('❌ renderSunburstFromConfig 오류:', e);
                // 오류 시 백업 방법 사용
                createSunburstFromData(data.portfolio_allocation);
            }
        }
        
        // ⭐ Sunburst 차트를 직접 생성하는 함수 (백업용) - 3단계 구조
        function createSunburstFromData(portfolio) {
            console.log('[createSunburstFromData] 함수 호출됨');
            console.log('[DEBUG] portfolio:', portfolio);
            
            if (!portfolio || portfolio.length === 0) {
                console.error('❌ portfolio_allocation이 비어있습니다');
                return;
            }
            
            console.log(`✅ portfolio 데이터 있음 (${portfolio.length}개 종목)`);
            
            const colorMap = {
                '반도체': '#4A5FC1',
                '바이오': '#5C3D7C',
                '방산': '#C94E8C',
                '통신': '#2A7FBA',
                '원자력': '#2D8F5C',
                '전력망': '#D63D5C',
                '조선': '#DAA520',
                'AI': '#FF6B9D',
                '기타': '#1B8B8B'
            };
            
            function lightenColor(hex, level) {
                if (hex.startsWith('rgb')) return hex;
                
                let r = parseInt(hex.slice(1, 3), 16);
                let g = parseInt(hex.slice(3, 5), 16);
                let b = parseInt(hex.slice(5, 7), 16);
                
                const factor = 1 + (level * 0.15);
                r = Math.min(255, Math.floor(r * factor));
                g = Math.min(255, Math.floor(g * factor));
                b = Math.min(255, Math.floor(b * factor));
                
                return `rgb(${r},${g},${b})`;
            }
            
            // 데이터 구조 생성
            const labels = [];
            const parents = [];
            const values = [];
            const colors = [];
            
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
            
            console.log(`포트폴리오 총 비중: ${totalPortfolioValue.toFixed(1)}%`);
            
            // 2. 섹터들 추가 (부모: 포트폴리오)
            Object.entries(sectorMap).forEach(([sector, stocks]) => {
                labels.push(sector);
                parents.push('포트폴리오');  // 부모는 포트폴리오
                
                // 섹터 총 비중 계산
                const sectorTotal = stocks.reduce((sum, stock) => sum + ((stock.weight || 0) * 100), 0);
                values.push(sectorTotal);
                colors.push(colorMap[sector] || '#1B8B8B');
                
                console.log(`섹터: ${sector} (${sectorTotal.toFixed(1)}%)`);
            });
            
            // 3. 종목들 추가 (부모: 각 섹터)
            Object.entries(sectorMap).forEach(([sector, stocks]) => {
                stocks.forEach((stock, idx) => {
                    const stockName = stock.name || stock.ticker;
                    const stockWeight = (stock.weight || 0) * 100;
                    
                    labels.push(stockName);
                    parents.push(sector);  // 부모는 섹터
                    values.push(stockWeight);
                    
                    // 밝은 색상
                    const baseColor = colorMap[sector] || '#1B8B8B';
                    const lighterColor = lightenColor(baseColor, idx);
                    colors.push(lighterColor);
                    
                    console.log(`  - ${stockName}: ${stockWeight.toFixed(1)}% (${lighterColor})`);
                });
            });
            
            console.log('[DEBUG] labels:', labels);
            console.log('[DEBUG] values:', values);
            
            // Plotly로 차트 생성
            const chartData = [{
                type: 'sunburst',
                labels: labels,
                parents: parents,
                values: values,
                branchvalues: 'total',  // 🔥 완전한 원형을 위해 'total' 사용
                marker: {
                    colors: colors,
                    line: { color: 'white', width: 2 }
                },
                textfont: { size: 12, color: 'white', family: 'Pretendard, Arial, sans-serif' },
                textinfo: 'label',  // 🔥 라벨만 표시
                hovertemplate: '<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
                maxdepth: 3,  // 🔥 3단계 구조 지원
                rotation: 0,
                sort: false
            }];
            
            const layout = {
                margin: { l: 20, r: 20, t: 20, b: 20 },
                font: { family: 'Pretendard, sans-serif', size: 14 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                autosize: true,
                width: null,
                height: 350  // PDF 호환성을 위해 크기 축소
            };
            
            try {
                Plotly.newPlot('sectorChart', chartData, layout, {
                    responsive: true,
                    displayModeBar: false,
                    staticPlot: false
                });
                console.log('[OK] 3단계 Sunburst 차트 생성 완료 (클라이언트 백업)');
            } catch (e) {
                console.error('[ERROR] Plotly.newPlot 오류:', e);
            }
        }
        
        // ⭐ 수익률 차트 전용 함수 - Plotly.js로 변경
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
            
            console.log('✅ performanceChart 발견, Plotly 차트 생성 중...');
            
            try {
                // Plotly 라인 차트 데이터
                const chartData = [
                    {
                        x: perfData.months.map(m => m + '개월'),
                        y: perfData.portfolio,
                        type: 'scatter',
                        mode: 'lines+markers',
                        name: '포트폴리오',
                        line: {
                            color: '#667eea',
                            width: 3,
                            shape: 'spline'
                        },
                        fill: 'tonexty',
                        fillcolor: 'rgba(102, 126, 234, 0.1)',
                        marker: {
                            color: '#667eea',
                            size: 6
                        },
                        hovertemplate: '<b>포트폴리오</b><br>기간: %{x}<br>수익률: %{y:.1f}%<extra></extra>'
                    },
                    {
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
                        fill: 'tozeroy',
                        fillcolor: 'rgba(153, 153, 153, 0.1)',
                        marker: {
                            color: '#999',
                            size: 5
                        },
                        hovertemplate: '<b>벤치마크 (KOSPI)</b><br>기간: %{x}<br>수익률: %{y:.1f}%<extra></extra>'
                    }
                ];
                
                const layout = {
                    margin: { l: 60, r: 20, t: 20, b: 60 },
                    font: { 
                        family: 'Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif', 
                        size: 12 
                    },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)',
                    autosize: true,
                    width: null,
                    height: 350,  // PDF 호환성을 위해 크기 축소
                    xaxis: {
                        title: {
                            text: '투자 기간',
                            font: { size: 14, color: '#333' }
                        },
                        showgrid: true,
                        gridcolor: 'rgba(0,0,0,0.1)',
                        zeroline: false
                    },
                    yaxis: {
                        title: {
                            text: '수익률 (%)',
                            font: { size: 14, color: '#333' }
                        },
                        showgrid: true,
                        gridcolor: 'rgba(0,0,0,0.1)',
                        zeroline: true,
                        zerolinecolor: '#666',
                        ticksuffix: '%'
                    },
                    legend: {
                        x: 0.02,
                        y: 0.98,
                        bgcolor: 'rgba(255,255,255,0.8)',
                        bordercolor: '#ddd',
                        borderwidth: 1,
                        font: { size: 12 }
                    },
                    showlegend: true
                };
                
                // Plotly로 차트 생성
                Plotly.newPlot('performanceChart', chartData, layout, {
                    responsive: true,
                    displayModeBar: false,
                    staticPlot: false
                });
                
                console.log('✅ Plotly 수익률 차트 생성 완료');
                
            } catch (e) {
                console.error('❌ Plotly 수익률 차트 생성 오류:', e);
            }
        }
    </script>
</body>
</html>
"""

@app.post("/api/download-pdf")
async def download_pdf(request: dict):
    """Playwright를 사용한 PDF 다운로드 (JavaScript 실행 지원)"""
    try:
        # 요청 데이터 검증
        html_content = request.get("html")
        if not html_content:
            print("❌ HTML 데이터 없음")
            raise HTTPException(status_code=400, detail="HTML 데이터가 없습니다")
        
        print(f"✅ HTML 데이터 수신 (길이: {len(html_content)} 문자)")
        
        # ⭐ 한글 폰트 및 차트 표시용 CSS 추가
        font_css = """
        <style>
            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
            * {
                font-family: 'Malgun Gothic', '맑은 고딕', Pretendard, sans-serif !important;
            }
            /* PDF용 최적화 */
            @media print {
                .btn-primary { display: none !important; }
                #downloadPdfBtn { display: none !important; }
                .chart-container { 
                    height: 320px !important;  /* 약간 더 크게 조정 */
                    margin: 15px 0 !important;
                    page-break-inside: auto;
                    overflow: visible;  /* 텍스트 잘림 방지 */
                }
                .section {
                    page-break-inside: auto;
                    margin-bottom: 20px !important;
                }
                #sectorChart, #performanceChart {
                    height: 320px !important;
                    width: 100% !important;
                }
                /* Plotly.js PDF 호환성 개선 */
                .plotly-graph-div {
                    height: 320px !important;
                }
                /* 폰트 크기 조정 */
                .plotly-graph-div text {
                    font-size: 14px !important;
                    font-family: 'Malgun Gothic', Arial, sans-serif !important;
                }
            }
        </style>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        """
        
        # HTML head에 폰트 CSS 추가
        html_with_font = html_content.replace('<head>', '<head>' + font_css)
        
        # ⭐ Playwright로 PDF 생성 (동기식으로 변경)
        print("🔄 Playwright 브라우저 시작...")
        
        def generate_pdf():
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                print("✅ 브라우저 페이지 생성 완료")
                
                # HTML 콘텐츠 설정
                page.set_content(html_with_font)
                print("✅ HTML 콘텐츠 설정 완료")
                
                # JavaScript 실행 완료까지 대기 (차트 렌더링 포함)
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(3000)  # 기본 대기
                
                # Plotly 라이브러리 로드 확인
                try:
                    page.evaluate("typeof Plotly !== 'undefined'")
                    print("✅ Plotly.js 로드 확인")
                except:
                    print("⚠️ Plotly.js 로드 대기 중...")
                    page.wait_for_timeout(2000)
                
                # 차트 요소 존재 확인 (JavaScript 오류 방지)
                try:
                    page.evaluate("""
                        () => {
                            const sectorChart = document.getElementById('sectorChart');
                            const performanceChart = document.getElementById('performanceChart');
                            if (!sectorChart || !performanceChart) {
                                throw new Error('차트 요소를 찾을 수 없습니다');
                            }
                            return true;
                        }
                    """)
                    print("✅ 차트 요소 존재 확인")
                except Exception as e:
                    print(f"⚠️ 차트 요소 없음: {e}")
                    # 차트가 없어도 PDF 생성 계속 진행
                
                # PDF 생성
                pdf_bytes = page.pdf(
                    format='A4',
                    landscape=False,  # 세로 방향
                    margin={
                        'top': '15mm',
                        'right': '15mm',
                        'bottom': '15mm',
                        'left': '15mm'
                    },
                    print_background=True,  # 배경색/이미지 포함
                    prefer_css_page_size=True
                )
                
                browser.close()
                print("✅ PDF 생성 완료")
                return pdf_bytes
        
        # 동기 함수를 별도 스레드에서 실행
        import asyncio
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(executor, generate_pdf)
        # 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"portfolio_analysis_{timestamp}.pdf"
        print(f"✅ PDF 생성 완료: {filename}")
        
        # 응답 생성
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    except HTTPException as http_err:
        # HTTP 예외는 그대로 전달
        raise http_err
    except Exception as e:
        # 기타 예외 처리
        print(f"❌ PDF 생성 중 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF 생성 오류: {str(e)}")

# =====================================================
# 실행
# =====================================================

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 AI 포트폴리오 분석 시스템 시작")
    print("="*60)
    print("📍 http://localhost:8000 에서 확인하세요")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
