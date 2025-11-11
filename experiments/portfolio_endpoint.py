"""
main.py

Portfolio Analysis System v2 - 고도화된 입출력 구조
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

from agent_test.portfolio_agent_anthropic import run_portfolio_agent, AVAILABLE_STOCKS, SECTORS

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
            return JSONResponse(content={
                "success": True,
                "report": result["final_report"],
                "iterations": result["iterations"]
            })
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


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
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
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
            height: 400px;
            margin: 20px 0;
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
                    <!-- 1. 투자 예산 -->
                    <div class="form-group">
                        <label>💰 총 투자 예산 (원)</label>
                        <input type="number" name="budget" value="5000000" 
                               min="1000000" step="100000" required>
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
                    
                    <!-- 5. 분석 엔진 -->
                    <div class="form-group">
                        <label>🔧 분석 AI 엔진</label>
                        <select name="model_name" required>
                            <option value="gpt-4o-mini" selected>GPT-4o Mini (빠름, 경제적)</option>
                            <option value="gpt-4o">GPT-4o (고성능, 정확)</option>
                            <option value="solar-pro">Solar Pro (대안)</option>
                        </select>
                    </div>
                    
                    <!-- 6. 추가 프롬프트 -->
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
        
        // 종목 리스트 로드
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
        
        // 선택 개수 업데이트
        function updateCount(type) {
            const count = document.querySelectorAll(`input[name="${type}"]:checked`).length;
            document.getElementById(`${type}Count`).textContent = `선택: ${count}개`;
        }
        
        // 폼 제출
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
                investment_targets: {
                    sectors: selectedSectors,
                    tickers: selectedStocks
                },
                risk_profile: formData.get('risk_profile'),
                investment_period: formData.get('investment_period'),
                model_name: formData.get('model_name'),
                additional_prompt: formData.get('additional_prompt') || ""
            };
            
            // UI 상태 변경
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
                const jsonMatch = reportText.match(/```json\s*([\s\S]*?)\s*```/);
                if (jsonMatch) {
                    data = JSON.parse(jsonMatch[1]);
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
                    ✅ 분석 완료 (${iterations}회 반복)
                </div>
                
                <!-- 1. AI 종합 요약 -->
                <div class="section">
                    <div class="section-title">🎯 AI 종합 브리핑</div>
                    <div class="summary-box">${data.ai_summary || '분석 요약 정보 없음'}</div>
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
                                <td><strong style="color: #667eea; font-size: 1.1em;">${avgScore}점</strong></td>
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
                    <div class="section-title">🥧 포트폴리오 구성 (섹터별 → 종목별)</div>
                    <div class="chart-container">
                        <div id="sectorChart" style="height: 500px;"></div>
                    </div>
                </div>
                
                <!-- 6. 예상 수익률 차트 -->
                <div class="section">
                    <div class="section-title">📊 예상 수익률 추이 (벤치마크 비교)</div>
                    <div class="chart-container">
                        <canvas id="performanceChart"></canvas>
                    </div>
                </div>
            `;
            
            document.getElementById('resultContent').innerHTML = html;
            document.getElementById('resultContent').classList.add('active');
            
            // 차트 렌더링
            renderCharts(data);
        }
        
        // 차트 렌더링
        function renderCharts(data) {
            // 1. 섹터 비중 Sunburst 차트로 변경
            if (data.portfolio_allocation) {
                // Sunburst 데이터 구조화
                const labels = ['포트폴리오'];  // 루트
                const parents = [''];
                const values = [100];
                const colors = [];
                
                const sectorMap = {};
                const colorMap = {
                    '반도체': '#667eea',
                    '바이오': '#764ba2',
                    '방산': '#f093fb',
                    '통신': '#4facfe',
                    '원자력': '#43e97b',
                    '전력망': '#fa709a',
                    '조선': '#fee140',
                    '기타': '#30cfd0'
                };
                
                // 섹터별로 종목 그룹화
                data.portfolio_allocation.forEach(stock => {
                    const sector = stock.sector || '기타';
                    if (!sectorMap[sector]) {
                        sectorMap[sector] = [];
                    }
                    sectorMap[sector].push(stock);
                });
                
                // 섹터 레이어 추가
                for (const [sector, stocks] of Object.entries(sectorMap)) {
                    const sectorWeight = stocks.reduce((sum, s) => sum + s.weight, 0);
                    labels.push(sector);
                    parents.push('포트폴리오');
                    values.push(sectorWeight * 100);
                    colors.push(colorMap[sector] || '#30cfd0');
                    
                    // 종목 레이어 추가 (안쪽 섹터 안에)
                    stocks.forEach(stock => {
                        labels.push(stock.name || stock.ticker);
                        parents.push(sector);
                        values.push(stock.weight * 100);
                        colors.push(colorMap[sector] || '#30cfd0');
                    });
                }
                
                // Plotly Sunburst 차트 렌더링
                const trace = {
                    type: 'sunburst',
                    labels: labels,
                    parents: parents,
                    values: values,
                    marker: {
                        colors: colors,
                        line: {
                            color: 'white',
                            width: 2
                        }
                    },
                    textposition: 'inside',
                    hovertemplate: '<b>%{label}</b><br>비중: %{value:.1f}%<extra></extra>',
                    textfont: {
                        size: 13,
                        color: 'white'
                    }
                };
                
                const layout = {
                    margin: {
                        l: 0,
                        r: 0,
                        t: 0,
                        b: 0
                    },
                    font: {
                        family: 'Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif'
                    },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)'
                };
                
                // ⭐ 핵심: DOM 요소가 존재하는지 확인
                const chartElement = document.getElementById('sectorChart');
                if (chartElement) {
                    Plotly.newPlot('sectorChart', [trace], layout, {responsive: true});
                } else {
                    console.error('❌ sectorChart 요소를 찾을 수 없습니다');
                }
            }
            
            // 2. 수익률 라인 차트 (기존 코드 유지)
            if (data.chart_data && data.chart_data.expected_performance) {
                const perfData = data.chart_data.expected_performance;
                
                const perfCtx = document.getElementById('performanceChart');
                if (!perfCtx) {
                    console.error('❌ performanceChart 요소를 찾을 수 없습니다');
                    return;
                }
                
                new Chart(perfCtx.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels: perfData.months.map(m => m + '개월'),
                        datasets: [
                            {
                                label: '포트폴리오',
                                data: perfData.portfolio,
                                borderColor: '#667eea',
                                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: '벤치마크 (KOSPI)',
                                data: perfData.benchmark,
                                borderColor: '#999',
                                backgroundColor: 'rgba(153, 153, 153, 0.1)',
                                borderWidth: 2,
                                borderDash: [5, 5],
                                tension: 0.4,
                                fill: true
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top',
                                labels: {
                                    font: { size: 14 },
                                    usePointStyle: true,
                                    padding: 15
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
                                    }
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                },
                                title: {
                                    display: true,
                                    text: '수익률 (%)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '투자 기간'
                                }
                            }
                        }
                    }
                });
            }
        }
        
        // 초기 로드
        loadSectors();
        loadStocks();            
    </script>
</body>
</html>
"""

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