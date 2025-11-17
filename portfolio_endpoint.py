"""
main.py

Portfolio Analysis System v2 - 고도화된 입출력 구조
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import plotly.graph_objects as go
from plotly.io import to_html
import json
import re
import traceback
# import pdfkit  # ⭐ 제거됨
from playwright.sync_api import sync_playwright
import io
from datetime import datetime

from agent_test.portfolio_agent_anthropic import run_portfolio_agent, AVAILABLE_STOCKS, SECTORS
from agent_test.portfolio_agent_langgraph import run_portfolio_agent_langgraph
from agent_test.portfolio_agent_multi import run_multi_agent_portfolio

from core.llm_clients import AVAILABLE_MODELS

app = FastAPI(title="AI 투자 포트폴리오 분석 시스템 v2")

# 정적 파일 (CSS, JS) 서빙 설정
app.mount("/static", StaticFiles(directory="experiments/templates"), name="static")


# =====================================================
# Request Model
# =====================================================

class InvestmentTargets(BaseModel):
    sectors: List[str] = Field(default=[], description="선택한 섹터 리스트")
    tickers: List[str] = Field(default=[], description="선택한 종목 티커 리스트")

class PortfolioRequest(BaseModel):
    budget: int = Field(..., ge=1000000, description="투자 예산")
    investment_targets: dict = Field(..., description="투자 대상 (섹터/종목)")
    risk_profile: Literal["안정", "중립", "공격"] = Field(..., description="투자 성향")
    investment_period: Literal["단기", "중기", "장기"] = Field(..., description="투자 기간")
    model_name: Literal["solar-pro2", "gpt-4o-mini", "gpt-4o", "gemini-2.5-pro"] = Field(default="gpt-4o-mini", description="분석 엔진")
    additional_prompt: Optional[str] = Field(default="", description="추가 요구사항")


# =====================================================
# API Endpoints
# =====================================================

@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse("experiments/templates/index.html")

@app.get("/test-multi-agent", response_class=FileResponse)
async def test_multi_agent():
    """멀티 에이전트 테스트 페이지"""
    return FileResponse("experiments/templates/test_multi_agent.html")

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


# =====================================================
# 공통 파싱 함수
# =====================================================

def parse_agent_result(result, engine="anthropic"):
    """Anthropic과 LangGraph 결과를 통합 처리하는 파싱 함수
    
    Args:
        result: Agent 실행 결과 (dict 또는 string)
        engine: "anthropic" 또는 "langgraph"
    
    Returns:
        dict: 파싱된 데이터 구조
    """
    # 1. LangGraph 방식 (이미 구조화된 딕셔너리)
    if engine == "langgraph" and isinstance(result, dict) and "portfolio_allocation" in result:
        return {
            "ai_summary": result.get("ai_summary"),
            "portfolio_allocation": result.get("portfolio_allocation"),
            "performance_metrics": result.get("performance_metrics"),
            "chart_data": result.get("chart_data"),
            "discussion_history": result.get("discussion_history", [])  # ⭐ 멀티에이전트 전문가 의견
        }
    
    # 2. Anthropic 방식 (문자열 파싱 필요)
    report_text = result.get("final_report", "") if isinstance(result, dict) else str(result)
    
    if not report_text:
        return _get_default_data()
    
    data = None
    
    # 2-1: ```json 블록 찾기
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', report_text)
    if json_match:
        json_str = json_match.group(1).strip()
        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            pass
    
    # 2-2: 직접 JSON 파싱 시도
    try:
        data = json.loads(report_text)
        return data
    except json.JSONDecodeError as e:
        pass
    
    # 3. 실패 시 기본값
    return _get_default_data()


def _get_default_data():
    """파싱 실패 시 기본 데이터 반환"""
    return {
        "ai_summary": "분석 결과를 불러올 수 없습니다.",
        "portfolio_allocation": [],
        "performance_metrics": {},
        "chart_data": {}
    }


# =====================================================
# 분석 엔드포인트
# =====================================================

@app.post("/api/analyze/anthropic")
async def analyze_anthropic(request: PortfolioRequest):
    """Anthropic 엔진으로 포트폴리오 분석"""
    try:
        print(f"\n{'='*60}")
        print(f"🌟 Anthropic 분석 요청")
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
            # 공통 파싱 함수 사용
            data = parse_agent_result(result, engine="anthropic")
            
            # 차트 생성 및 데이터 추가
            data = _add_chart_data(data)
            
            return JSONResponse(content={
                "success": True,
                "report": json.dumps(data, ensure_ascii=False),
                "iterations": result.get("iterations", 1)
            })
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "알 수 없는 오류"))
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


# @app.post("/api/analyze/langgraph")
# async def analyze_langgraph(request: Request):
#     """멀티 에이전트로 포트폴리오 분석 """
#     try:
#         # ⭐ 요청 데이터 확인용 로그
#         body = await request.json()
#         print("\n" + "="*60)
#         print("📥 받은 요청 데이터:")
#         print(json.dumps(body, ensure_ascii=False, indent=2))
#         print("="*60 + "\n")
        
#         # ⭐ Pydantic 모델로 수동 파싱
#         try:
#             portfolio_req = PortfolioRequest(**body)
#         except Exception as e:
#             print(f"❌ Pydantic 검증 실패: {e}")
#             raise HTTPException(status_code=422, detail=f"요청 데이터 형식 오류: {str(e)}")
        
#         print(f"\n{'='*60}")
#         print(f"🤖 멀티 에이전트 분석 요청 (LangGraph 엔드포인트)")
#         print(f"  예산: {request.budget:,}원")
#         print(f"  섹터: {request.investment_targets.sectors}")
#         print(f"  종목: {request.investment_targets.tickers}")
#         print(f"  성향: {request.risk_profile}")
#         print(f"  기간: {request.investment_period}")
#         print(f"{'='*60}\n")
        
#         result = run_multi_agent_portfolio(
#             budget=request.budget,
#             investment_targets={
#                 "sectors": request.investment_targets.sectors,
#                 "tickers": request.investment_targets.tickers
#             },
#             risk_profile=request.risk_profile,
#             investment_period=request.investment_period,
#             additional_prompt=request.additional_prompt,
#             model_name=request.model_name  # ⭐ 모델 선택 추가
#         )
        
#         if result["success"]:
#             # 공통 파싱 함수 사용
#             data = parse_agent_result(result, engine="langgraph")
            
#             # 차트 생성 및 데이터 추가
#             data = _add_chart_data(data)
            
#             return JSONResponse(content={
#                 "success": True,
#                 "report": json.dumps(data, ensure_ascii=False),
#                 "iterations": 1
#             })
#         else:
#             raise HTTPException(status_code=500, detail=result.get("error", "알 수 없는 오류"))
    
#     except Exception as e:
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@app.post("/api/analyze/langgraph")
async def analyze_langgraph(request: Request):
    try:
        body = await request.json()
        
        budget = body.get("budget")
        investment_targets = body.get("investment_targets", {})
        risk_profile = body.get("risk_profile")
        investment_period = body.get("investment_period")
        model_name = body.get("model_name", "solar-pro2")
        additional_prompt = body.get("additional_prompt", "")
        
        print("\n===== LangGraph 분석 요청 =====")
        print(f"  예산: {budget:,}원")
        print(f"  섹터: {investment_targets.get('sectors', [])}")
        print(f"  종목: {investment_targets.get('tickers', [])}")
        print(f"  성향: {risk_profile}")
        print(f"  기간: {investment_period}")
        print(f"  모델: {model_name}")
        print(f"  추가 프롬프트: {additional_prompt}")
        
        # ... 여기서부터 기존 분석 함수 사용 ...
        result = run_multi_agent_portfolio(
            budget=budget,
            investment_targets=investment_targets,
            risk_profile=risk_profile,
            investment_period=investment_period,
            additional_prompt=additional_prompt,
            model_name=model_name
        )
        
        # 결과 반환
        return JSONResponse(content={
                "success": True,
                "report": json.dumps(result, ensure_ascii=False),
                "iterations": 1
            })
        
    except Exception as e:
        print("에러:", e)
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")



def _add_chart_data(data):
    """차트 HTML 및 설정 추가하는 공통 함수"""
    # Sunburst 차트 생성
    sunburst_chart, chart_config = create_sunburst_chart(data)
    
    # 차트를 HTML로 변환
    chart_html = to_html(
        sunburst_chart, 
        include_plotlyjs='cdn',
        full_html=False,
        div_id="sectorChart"
    )
    
    # chart_data 구조 생성 (수익률 차트용)
    chart_data = {}
    
    # 기존 데이터에서 수익률 정보 추출
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
        
    elif 'months' in data and 'portfolio' in data and 'benchmark' in data:
        chart_data['expected_performance'] = {
            'months': data['months'],
            'portfolio': data['portfolio'], 
            'benchmark': data['benchmark']
        }
    else:
        chart_data['expected_performance'] = None
    
    # 데이터에 차트 추가
    data['chart_html'] = chart_html
    data['chart_config'] = chart_config
    data['chart_data'] = chart_data
    
    return data

def create_sunburst_chart(data):
    """3단계 구조의 완전한 원형 Sunburst 차트 생성"""
    
    portfolio = data.get('portfolio_allocation', [])
    
    if not portfolio:
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
    
    # === 3단계 구조: 포트폴리오 → 섹터 → 종목 ===
    
    # 1. 루트 노드 "포트폴리오" 추가
    total_portfolio_value = sum((stock.get('weight', 0) * 100) for stock in portfolio)
    labels.append('포트폴리오')
    parents.append('')  # 최상위 루트
    values.append(total_portfolio_value)
    colors.append('#FFFFFF')  # 포트폴리오 색상 (흰색)
    
    # 2. 섹터들 추가 (부모: 포트폴리오)
    for sector, stocks in sector_map.items():
        labels.append(sector)
        parents.append('포트폴리오')  # 부모는 포트폴리오
        
        # 섹터의 총 비중 계산
        sector_total = sum((stock.get('weight', 0) * 100) for stock in stocks)
        values.append(sector_total)
        colors.append(colorMap.get(sector, '#1B8B8B'))
    
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
        textfont=dict(size=12, color='white', family='Pretendard, Arial, sans-serif'),  # ⭐ 흰색
        textinfo='label',  # ⭐ 라벨만 표시
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
        height=400  # ⭐ 390 → 400으로 10px 증가
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
            'height': 400  # ⭐ 390 → 400으로 10px 증가
        }
    }
    
    return fig_sunburst, chart_config

@app.post("/api/download-pdf")
async def download_pdf(request: dict):
    """Playwright를 사용한 PDF 다운로드 (JavaScript 실행 지원)"""
    try:
        # 요청 데이터 검증
        html_content = request.get("html")
        if not html_content:
            raise HTTPException(status_code=400, detail="HTML 데이터가 없습니다")
        
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
                    height: 350px !important;  /* ⭐ PDF용 높이 증가 (300 → 350) */
                    margin: 20px 0 !important;  /* ⭐ 상하 여백 증가 */
                    page-break-inside: avoid;  /* ⭐ 페이지 분할 방지 */
                    overflow: visible;
                }
                .section {
                    page-break-inside: avoid;  /* ⭐ 섹션 분할 방지 */
                    margin-bottom: 30px !important;  /* ⭐ 섹션 간 여백 증가 */
                }
                #sectorChart, #performanceChart {
                    height: 320px !important;  /* ⭐ 실제 차트 높이 증가 (280 → 320) */
                    width: 100% !important;
                }
                /* Plotly.js PDF 호환성 개선 */
                .plotly-graph-div {
                    height: 320px !important;  /* ⭐ Plotly div 높이 증가 (280 → 320) */
                    page-break-inside: avoid;
                }
                /* 폰트 크기 조정 */
                .plotly-graph-div text {
                    font-size: 11px !important;  /* ⭐ 폰트 크기 감소 */
                    font-family: 'Malgun Gothic', Arial, sans-serif !important;
                }
                /* 투자 책임 경고 - PDF용 */
                .disclaimer {
                    background: #fff3cd !important;
                    border: 2px solid #ffc107 !important;
                    border-radius: 8px !important;
                    padding: 15px !important;
                    margin-top: 30px !important;
                    page-break-inside: avoid !important;
                }
                .disclaimer p {
                    font-size: 10px !important;
                    line-height: 1.5 !important;
                    color: #333 !important;
                }
            }
        </style>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        """
        
        # HTML head에 폰트 CSS 추가
        html_with_font = html_content.replace('<head>', '<head>' + font_css)
        
        # ⭐ Playwright로 PDF 생성 (동기식으로 변경)
        def generate_pdf():
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                
                # HTML 콘텐츠 설정
                page.set_content(html_with_font)
                
                # JavaScript 실행 완료까지 대기 (차트 렌더링 포함)
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(3000)  # 기본 대기
                
                # Plotly 라이브러리 로드 확인
                try:
                    page.evaluate("typeof Plotly !== 'undefined'")
                except:
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
                except Exception as e:
                    # 차트가 없어도 PDF 생성 계속 진행
                    pass
                
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
                return pdf_bytes
        
        # 동기 함수를 별도 스레드에서 실행
        import asyncio
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(executor, generate_pdf)
        # 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"portfolio_analysis_{timestamp}.pdf"
        
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF 생성 오류: {str(e)}")

@app.post("/api/analyze/multi-agent")
async def analyze_portfolio_multi_agent(request: PortfolioRequest):
    """멀티 에이전트 포트폴리오 분석"""
    result = run_multi_agent_portfolio(
        budget=request.budget,
        investment_targets=request.investment_targets,
        risk_profile=request.risk_profile,
        investment_period=request.investment_period,
        additional_prompt=request.additional_prompt
    )
    return result

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
