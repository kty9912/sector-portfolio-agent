from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import plotly.graph_objects as go
from plotly.io import to_html
import json
import os
import re
import traceback
from pathlib import Path
from playwright.sync_api import sync_playwright
import io
from datetime import datetime
import time

from agents.portfolio_agent_anthropic import run_portfolio_agent, get_sectors as get_sectors_list, get_available_stocks
from agents.portfolio_agent_multi import run_multi_agent_portfolio
from agents.stock_agent_anthropic import run_stock_analysis_agent
from agents.stock_agent_langgraph import run_langgraph_stock_analysis
from core.llm_clients import AVAILABLE_MODELS

import sys
sys.stdout.reconfigure(line_buffering=True)

app = FastAPI(title="AI 투자 포트폴리오 분석 시스템 v2")

# 정적 파일 (CSS, JS) 서빙 설정
app.mount("/static", StaticFiles(directory="templates"), name="static")

# ------------------------------
#  환경 설정
# ------------------------------
CERT_PATH = r"C:\certs\cacert.pem"
if os.path.exists(CERT_PATH):
    os.environ['CURL_CA_BUNDLE'] = CERT_PATH
    os.environ['SSL_CERT_FILE'] = CERT_PATH
    os.environ['REQUESTS_CA_BUNDLE'] = CERT_PATH
else:
    print(f"⚠️ 경고: {CERT_PATH} 파일이 없습니다. yfinance가 작동하지 않을 수 있습니다.")
    print("해결: python experiments/fix_cert_path.py 실행")

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

class StockAnalysisRequest(BaseModel):
    ticker: str = Field(..., description="종목 코드 (예: 005930.KS)")
    profile: Literal["aggressive", "balanced", "conservative"] = Field(
        default="balanced",
        description="투자 성향"
    )
    model_name: str = Field(
        default="gpt-4o",
        description="분석 모델"
    )

# =====================================================
# API Endpoints
# =====================================================
@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse("templates/index.html")

@app.get("/portfolio", response_class=FileResponse)
async def portfolio():
    return FileResponse("templates/portfolio.html")

@app.get("/stock", response_class=FileResponse)
async def stock():
    return FileResponse("templates/stock.html")

@app.get("/api/sectors")
async def get_sectors():
    """사용 가능한 섹터 리스트"""
    return {"sectors": get_sectors_list()}

@app.get("/api/stocks")
async def get_stocks():
    """전체 종목 리스트"""
    return {
        "stocks": [
            {"ticker": ticker, "name": name}
            for ticker, name in get_available_stocks()
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
# 분석 엔드포인트
# =====================================================

@app.post("/api/analyze/anthropic")
async def analyze_anthropic(request: Request):
    """Anthropic 엔진으로 포트폴리오 분석"""
    # ⭐ 타이머 시작
    start_time = time.time()
    start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        body = await request.json()
        
        budget = body.get("budget")
        investment_targets = body.get("investment_targets", {})
        risk_profile = body.get("risk_profile")
        investment_period = body.get("investment_period")
        model_name = body.get("model_name", "solar-pro2")
        additional_prompt = body.get("additional_prompt", "")
        
        print("\n===== Anthropic 분석 요청 =====")
        print(f"  예산: {budget:,}원")
        print(f"  섹터: {investment_targets.get('sectors', [])}")
        print(f"  종목: {investment_targets.get('tickers', [])}")
        print(f"  성향: {risk_profile}")
        print(f"  기간: {investment_period}")
        print(f"  모델: {model_name}")
        print(f"  추가 프롬프트: {additional_prompt}")
        
        result = run_portfolio_agent(
            budget=budget,
            investment_targets=investment_targets,
            risk_profile=risk_profile,
            investment_period=investment_period,
            model_name=model_name,
            additional_prompt=additional_prompt
        )
        

        #  타이머 종료
        end_time = time.time()
        elapsed_time = end_time - start_time
        end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 시간 포맷팅
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        #  로그 출력
        print(f"\n⏱️  분석 소요 시간: {minutes}분 {seconds}초 ({elapsed_time:.2f}초)")
        print(f"  시작: {start_datetime}")
        print(f"  종료: {end_datetime}")
        print("="*60 + "\n")


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
            # 에러 시에도 소요 시간 표시
            elapsed_time = time.time() - start_time
            print(f"\n❌ 에러 발생 (소요 시간: {elapsed_time:.2f}초): {result.get('error', '알 수 없는 오류')}")
            raise HTTPException(status_code=500, detail=result.get("error", "알 수 없는 오류"))
    
    except Exception as e:
        # 에러 시에도 소요 시간 표시
        elapsed_time = time.time() - start_time
        print(f"\n❌ 에러 발생 (소요 시간: {elapsed_time:.2f}초): {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@app.post("/api/analyze/langgraph")
async def analyze_langgraph(request: Request):
    """LangGraph 엔진으로 포트폴리오 분석"""
    # ⭐ 타이머 시작
    start_time = time.time()
    start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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


        # 타이머 종료
        end_time = time.time()
        elapsed_time = end_time - start_time
        end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 시간 포맷팅
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        #  로그 출력
        print(f"\n⏱️  분석 소요 시간: {minutes}분 {seconds}초 ({elapsed_time:.2f}초)")
        print(f"  시작: {start_datetime}")
        print(f"  종료: {end_datetime}")
        print("="*60 + "\n")

        
        # 결과 반환
        return JSONResponse(content={
                "success": True,
                "report": json.dumps(result, ensure_ascii=False),
                "iterations": 1
            })
        
    except Exception as e:
        print("에러:", e)
        # 에러 시에도 소요 시간 표시
        elapsed_time = time.time() - start_time
        print(f"\n❌ 에러 발생 (소요 시간: {elapsed_time:.2f}초): {e}")
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

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
        '반도체': '#5c6bc0',
        '바이오': '#26a69a',
        '방산': '#78909c',
        '통신': '#7e57c2',
        '원자력': '#ef5350',
        '전력망': '#ffa726',
        '조선': '#42a5f5',
        'AI': '#7e57c2',
        '기타': '#26a69a'
    };
    
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

@app.post("/api/stock/anthropic")
async def analyze_stock_anthropic(request: StockAnalysisRequest):
    """Anthropic 기반 종목 분석"""
    try:
        result = run_stock_analysis_agent(
            ticker=request.ticker,
            profile=request.profile,
            model_name=request.model_name
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stock/langgraph")
async def analyze_stock_langgraph(request: StockAnalysisRequest):
    """LangGraph 기반 종목 분석"""
    try:
        result = run_langgraph_stock_analysis(
            ticker=request.ticker,
            profile=request.profile,
            model_name=request.model_name
        )
        return JSONResponse(content=result)
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quick-info/{ticker}")
async def get_quick_info(ticker: str):
    """종목 간단 정보 조회"""
    try:
        from core.db import fetch_one
        import yfinance as yf
        
        # DB 조회
        sql = "SELECT ticker, name_kr, market, industry FROM companies WHERE ticker = %s"
        row = fetch_one(sql, (ticker,))
        
        if row:
            name_kr = row[1]
            market = row[2]
            industry = row[3]
        else:
            # yfinance fallback
            stock = yf.Ticker(ticker)
            info = stock.info
            name_kr = info.get('longName', ticker)
            market = "KOSPI" if ".KS" in ticker else "KOSDAQ"
            industry = info.get('industry', 'Unknown')
        
        # 현재가
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        current_price = float(hist['Close'].iloc[-1]) if not hist.empty else 0
        
        return {
            "ticker": ticker,
            "name_kr": name_kr,
            "market": market,
            "industry": industry,
            "current_price": current_price
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chart-data/{ticker}")
async def get_chart_data(ticker: str):
    """차트용 데이터 조회 (주가 6개월 + 재무 4분기)"""
    try:
        print(f"\n{'='*60}")
        print(f"📊 차트 데이터 조회 요청: {ticker}")
        print(f"{'='*60}\n")
        
        from core.db import fetch_all
        from datetime import datetime, timedelta
        
        # 1. 주가 데이터 (6개월)
        six_months_ago = (datetime.now() - timedelta(days=180)).date()
        print(f"📅 조회 시작일: {six_months_ago}")
        
        price_sql = """
            SELECT date, close, volume
            FROM prices_daily
            WHERE ticker = %s AND date >= %s
            ORDER BY date
        """
        
        print(f"🔍 주가 데이터 조회 중...")
        price_rows = fetch_all(price_sql, (ticker, six_months_ago))
        print(f"✅ 주가 데이터 {len(price_rows)}개 조회됨")
        
        prices = []
        for row in price_rows:
            prices.append({
                "date": row[0].isoformat(),
                "close": float(row[1]) if row[1] else None,
                "volume": int(row[2]) if row[2] else None
            })
        
        # 2. 재무 데이터 (최근 4분기)
        financial_sql = """
            SELECT f.fiscal_date, f.revenue, f.op_income, f.net_income, 
                   f.total_liab, f.equity,
                   m.roe, m.debt_ratio
            FROM fundamentals f
            LEFT JOIN fin_metrics m ON f.ticker = m.ticker AND f.fiscal_date = m.fiscal_date AND f.freq = m.freq
            WHERE f.ticker = %s AND f.freq = 'Q'
            ORDER BY f.fiscal_date DESC
            LIMIT 4
        """
        
        print(f"🔍 재무 데이터 조회 중...")
        financial_rows = fetch_all(financial_sql, (ticker,))
        print(f"✅ 재무 데이터 {len(financial_rows)}개 조회됨")
        
        financials = []
        for row in financial_rows:
            # fiscal_date로부터 연도와 분기 추출 (예: 2024-03-31 -> 2024Q1)
            fiscal_date = row[0]
            if fiscal_date:
                year = fiscal_date.year
                month = fiscal_date.month
                quarter = (month - 1) // 3 + 1
                period = f"{year}Q{quarter}"
            else:
                period = "N/A"
            
            financials.append({
                "period": period,
                "revenue": float(row[1]) if row[1] else None,
                "operating_income": float(row[2]) if row[2] else None,
                "net_income": float(row[3]) if row[3] else None,
                "total_liab": float(row[4]) if row[4] else None,
                "equity": float(row[5]) if row[5] else None,
                "roe": float(row[6]) if row[6] else None,
                "debt_ratio": float(row[7]) if row[7] else None
            })
        
        # 최신순으로 정렬되어 있으므로 역순으로 변경 (시간순)
        financials.reverse()
        
        result = {
            "ticker": ticker,
            "prices": prices,
            "financials": financials
        }
        
        print(f"📦 반환 데이터: prices={len(prices)}개, financials={len(financials)}개\n")
        
        return result
    
    except Exception as e:
        print(f"❌ 차트 데이터 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-comparison/{ticker}")
async def get_sector_comparison(ticker: str):
    """섹터 내 밸류에이션 비교 데이터 조회"""
    try:
        print(f"\n{'='*60}")
        print(f"🔍 섹터 비교 데이터 조회: {ticker}")
        print(f"{'='*60}\n")
        
        from core.db import fetch_all, fetch_one
        
        # 1. 해당 종목의 섹터 확인
        sector_sql = """
            SELECT industry
            FROM companies
            WHERE ticker = %s
        """
        sector_row = fetch_one(sector_sql, (ticker,))
        
        if not sector_row:
            return {"error": "종목을 찾을 수 없습니다"}
        
        sector = sector_row[0]
        print(f"📊 섹터: {sector}")
        
        # 2. 같은 섹터의 다른 종목들 조회 (최대 5개)
        comparison_sql = """
            SELECT 
                c.ticker,
                c.name_kr,
                p.close as current_price,
                f.revenue,
                f.net_income,
                f.equity,
                f.ebitda,
                f.total_assets,
                m.roe
            FROM companies c
            LEFT JOIN (
                SELECT ticker, close
                FROM prices_daily
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM prices_daily
                    GROUP BY ticker
                )
            ) p ON c.ticker = p.ticker
            LEFT JOIN (
                SELECT ticker, revenue, net_income, equity, ebitda, total_assets
                FROM fundamentals
                WHERE (ticker, fiscal_date) IN (
                    SELECT ticker, MAX(fiscal_date)
                    FROM fundamentals
                    WHERE freq = 'Q'
                    GROUP BY ticker
                )
            ) f ON c.ticker = f.ticker
            LEFT JOIN (
                SELECT ticker, roe
                FROM fin_metrics
                WHERE (ticker, fiscal_date) IN (
                    SELECT ticker, MAX(fiscal_date)
                    FROM fin_metrics
                    WHERE freq = 'Q'
                    GROUP BY ticker
                )
            ) m ON c.ticker = m.ticker
            WHERE c.industry = %s
            ORDER BY f.revenue DESC NULLS LAST
            LIMIT 5
        """
        
        rows = fetch_all(comparison_sql, (sector,))
        print(f"✅ {len(rows)}개 종목 조회됨")
        
        comparisons = []
        for row in rows:
            # PER 계산: 주가 / EPS, EPS = net_income / shares (간단 추정)
            per = None
            pbr = None
            market_cap = None
            ev_ebitda = None
            
            current_price = float(row[2]) if row[2] else None
            revenue = float(row[3]) if row[3] else None
            net_income = float(row[4]) if row[4] else None
            equity = float(row[5]) if row[5] else None
            ebitda = float(row[6]) if row[6] else None
            total_assets = float(row[7]) if row[7] else None
            
            # 시가총액 추정 (equity * 2 정도로 간단 추정)
            if equity and equity > 0:
                market_cap = equity * 2.5
            
            # PBR 계산: 시가총액 / 자기자본
            if market_cap and equity and equity > 0:
                pbr = market_cap / equity
            
            # PER 계산: 시가총액 / 순이익
            if market_cap and net_income and net_income > 0:
                per = market_cap / net_income
            
            # EV/EBITDA 계산: 시가총액 / EBITDA (부채 고려 안함)
            if market_cap and ebitda and ebitda > 0:
                ev_ebitda = market_cap / ebitda
            
            comparisons.append({
                "ticker": row[0],
                "name": row[1],
                "current_price": current_price,
                "per": per,
                "pbr": pbr,
                "ev_ebitda": ev_ebitda,
                "market_cap": market_cap,
                "is_target": row[0] == ticker
            })
        
        result = {
            "ticker": ticker,
            "sector": sector,
            "comparisons": comparisons
        }
        
        print(f"📦 섹터 비교 데이터 반환: {len(comparisons)}개 종목\n")
        
        return result
    
    except Exception as e:
        print(f"❌ 섹터 비교 데이터 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# PDF 다운로드 엔드포인트
# =====================================================

@app.post("/api/stock/download-pdf")
async def download_pdf(request: dict):
    """Playwright를 사용한 PDF 다운로드"""
    try:
        html_content = request.get("html")
        if not html_content:
            raise HTTPException(status_code=400, detail="HTML 데이터가 없습니다")
        
        # 한글 폰트 및 PDF용 CSS 추가
        font_css = """
        <style>
            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
            * {
                font-family: 'Malgun Gothic', '맑은 고딕', Pretendard, sans-serif !important;
            }
            /* PDF용 폰트 크기 최적화 - 디자인은 유지 */
            @media print {
                /* 배경 제거 */
                body {
                    background: white !important;
                    padding: 20px !important;
                }
                .container {
                    background: white !important;
                    box-shadow: none !important;
                }
                .panel {
                    box-shadow: none !important;
                }
                
                /* 버튼 숨김 */
                .btn-primary { display: none !important; }
                #downloadPdfBtn { display: none !important; }
                details { display: none !important; }
                
                /* 이미지로 변환된 차트는 그대로 표시 */
                img {
                    page-break-inside: avoid;
                    max-width: 100% !important;
                    height: auto !important;
                }
                
                /* 섹션 - 페이지 분할 방지 */
                .section {
                    page-break-inside: avoid;
                }
                
                /* 그림자 제거 */
                .metric-card {
                    box-shadow: none !important;
                }
                .summary-box {
                    box-shadow: none !important;
                }
                .disclaimer {
                    box-shadow: none !important;
                }
                
                /* 헤더 섹션 폰트 크기 조정 */
                .stock-header > div:first-child {
                    font-size: 1.2em !important;  /* 제목 크기 축소 */
                }
                .stock-header > div:nth-child(2) {
                    font-size: 0.85em !important;
                }
                .stock-header > div:nth-child(3) {
                    font-size: 0.8em !important;
                }
                
                /* 폰트 크기만 줄임 (디자인은 유지) */
                .section-title {
                    font-size: 1.1em !important;  /* 섹션 제목 축소 */
                }
                .metric-label {
                    font-size: 0.75em !important;
                }
                .metric-value {
                    font-size: 1.2em !important;
                }
                .metric-unit {
                    font-size: 0.85em !important;
                }
                .summary-box {
                    font-size: 0.85em !important;
                    line-height: 1.5 !important;
                }
                .summary-box h3, .summary-box h4 {
                    font-size: 1.1em !important;
                }
                .summary-box p {
                    font-size: 0.85em !important;
                }
                
                /* 시나리오 비교 테이블 */
                table {
                    font-size: 0.8em !important;
                }
                table th {
                    font-size: 0.85em !important;
                }
                table td {
                    font-size: 0.8em !important;
                }
                
                /* 면책 조항 */
                .disclaimer {
                    page-break-inside: avoid !important;
                }
                .disclaimer p {
                    font-size: 0.75em !important;
                    line-height: 1.5 !important;
                }
                .disclaimer strong {
                    font-size: 0.85em !important;
                }
            }
        </style>
        """
        
        html_with_font = html_content.replace('<head>', '<head>' + font_css)
        
        # Playwright로 PDF 생성
        def generate_pdf():
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_with_font)
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2000)
                
                pdf_bytes = page.pdf(
                    format='A4',
                    landscape=False,
                    margin={
                        'top': '15mm',
                        'right': '15mm',
                        'bottom': '15mm',
                        'left': '15mm'
                    },
                    print_background=True,
                    prefer_css_page_size=True
                )
                
                browser.close()
                return pdf_bytes
        
        # 동기 함수를 별도 스레드에서 실행
        import asyncio
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(executor, generate_pdf)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stock_analysis_{timestamp}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        print(f"❌ PDF 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 2025 금융 투자 AI Agent 플랫폼")
    print("="*60)
    print("📍 http://localhost:8000 에서 확인하세요")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)