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
        const response = await fetch('/api/sectors');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
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
    } catch (error) {
        const sectorsList = document.getElementById('sectorsList');
        if (sectorsList) {
            sectorsList.innerHTML = '<p style="color: red;">섹터 로드 실패: ' + error.message + '</p>';
        }
    }
}

// 종목 리스트 로드
async function loadStocks() {
    try {
        const response = await fetch('/api/stocks');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
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
    } catch (error) {
        const stocksList = document.getElementById('stocksList');
        if (stocksList) {
            stocksList.innerHTML = '<p style="color: red;">종목 로드 실패: ' + error.message + '</p>';
        }
    }
}

// 사용 가능한 모델 목록 로드
async function loadAvailableModels() {
    try {
        const response = await fetch('/api/models');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        return data.models;
    } catch (error) {
        return ['claude-3-5-sonnet-20241022']; // 기본 fallback
    }
}

// AI 엔진 변경 시 모델 옵션 업데이트
async function updateModelOptions() {
    const selectedEngine = document.querySelector('input[name="aiEngine"]:checked').value;
    const modelSelect = document.getElementById('modelSelect');
    
    modelSelect.innerHTML = '<option value="">모델 로딩 중...</option>';
    
    try {
        const availableModels = await loadAvailableModels();
        
        modelSelect.innerHTML = availableModels.map(model => 
            `<option value="${model}">${getModelDisplayName(model)}</option>`
        ).join('');
    } catch (error) {
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

// 로딩 애니메이션 제어 객체
const LoadingController = {
    steps: [
        '데이터를 수집하고 있습니다',
        '주가를 분석하고 있습니다',
        '재무제표를 분석하고 있습니다',
        '관련 뉴스를 찾아보고 있습니다',
        '뉴스를 분석하고 있습니다',
        '점수를 산출하고 있습니다',
        '포트폴리오 구성을 분석하고 있습니다',
        '투자 전략을 최적화하고 있습니다',
        '전략 내용을 검수하고 있습니다',
        '포트폴리오 비율 차트를 그리고 있습니다',
        '수익률 그래프를 그리고 있습니다',
        '보고서를 작성하고 있습니다'
    ],
    currentStep: 0,
    interval: null,
    
    start: function() {
        this.currentStep = 0;
        this.updateStep();
        
        this.interval = setInterval(() => {
            this.currentStep = (this.currentStep + 1) % this.steps.length;
            this.updateStep();
        }, 2000);
    },
    
    updateStep: function() {
        const stepMessage = document.getElementById('stepMessage');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (stepMessage) {
            stepMessage.textContent = this.steps[this.currentStep];
        }
        
        const progress = Math.floor((this.currentStep / this.steps.length) * 100);
        
        if (progressFill) {
            progressFill.style.width = progress + '%';
        }
        
        if (progressText) {
            progressText.textContent = progress + '%';
        }
    },
    
    stop: function() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
        
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (progressFill) {
            progressFill.style.width = '100%';
        }
        
        if (progressText) {
            progressText.textContent = '100%';
        }
    }
};

// 포트폴리오 분석 실행 함수
function startLoadingAnimation() {
    LoadingController.start();
}

// 요청 처리
async function handleRegularRequest(apiEndpoint, requestData, selectedEngine) {
    try {
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(requestData)
        });
        
        const result = await response.json();
        console.log('result', result)
        
        if (result.success) {
            renderResults(result.report, result.iterations);
            LoadingController.stop();
        } else {
            throw new Error(result.detail || '분석 실패');
        }
    } catch (error) {
        console.error('분석 실패:', error);
        alert('분석 중 오류가 발생했습니다: ' + error.message);
        LoadingController.stop();
    }
}

// ⭐ DOM이 완전히 로드된 후 초기 함수 실행
document.addEventListener('DOMContentLoaded', function() {
    loadSectors();
    loadStocks();
    updateModelOptions();
    
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
    if (num <= 0) return '0원';

    const numKor = {'0': '', '1': '일', '2': '이', '3': '삼', '4': '사', '5': '오', '6': '육', '7': '칠', '8': '팔', '9': '구'};
    const sUnitKor = ['', '십', '백', '천'];
    const lUnitKor = ['', '만', '억', '조', '경'];

    let numStrList = num.toString().split('').reverse();

    let result = '';
    for(let i = 0; i < numStrList.length / 4; i++) {
        const char = numStrList.slice(i * 4, (i + 1) * 4).join('')
        if(char === '0000') continue;

        let part = '';
        for(let j = 0; j < char.length; j++) {
            const n = char.charAt(j);
            if(n === '0') continue;
            part = numKor[n] + sUnitKor[j] + part;
        }
        result = part + lUnitKor[i] + result;
    }

    return result + '원';
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
    const apiEndpoint = selectedEngine === 'langgraph' 
        ? '/api/analyze/langgraph' 
        : '/api/analyze/anthropic';
    
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
    
    // 로딩 애니메이션 시작
    startLoadingAnimation();
    
    // 선택된 엔진 표시
    const engineDisplay = selectedEngine === 'langgraph' ? 'LangGraph' : 'Anthropic';

    try {
        await handleRegularRequest(apiEndpoint, requestData, selectedEngine);
        
    } catch (error) {
        LoadingController.stop();
        
        document.getElementById('resultContent').innerHTML = `
            <div style="background: #fee; border: 2px solid #fcc; border-radius: 12px; padding: 30px; color: #c33;">
                <h3>❌ 오류 발생</h3>
                <p style="margin-top: 10px;">${error.message}</p>
            </div>
        `;
        document.getElementById('resultContent').classList.add('active');
    } finally {
        setTimeout(() => {
            document.getElementById('loadingState').style.display = 'none';
            document.getElementById('analyzeBtn').disabled = false;
        }, 1000);
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
        <!-- 1. AI 종합 요약 -->
        <div class="section">
            <div class="section-title">AI 종합 브리핑</div>
            <div class="summary-box">` + (data.ai_summary || '분석 요약 정보 없음') + `</div>
        </div>
    `;
    
    // ⭐ 멀티에이전트 전문가 의견 표시 (discussion_history가 있는 경우만)
    if (data.discussion_history && data.discussion_history.length > 0) {
        html += `
        <!-- 1.5. 전문가 분석 의견 -->
        <div class="section">
            <div class="section-title">전문가 분석 의견</div>
            <div style="display: grid; gap: 15px;">
        `;
        
        data.discussion_history.forEach((opinion, idx) => {
            // 전문가 타입 감지 (재무/기술/뉴스)
            let expertType = '전문가';
            let expertColor = '#667eea';
            
            if (opinion.includes('[재무 전문가]') || opinion.includes('Financial Agent')) {
                expertType = '재무 전문가';
                expertColor = '#28a745';
            } else if (opinion.includes('[기술 전문가]') || opinion.includes('Technical Agent')) {
                expertType = '기술 전문가';
                expertColor = '#007bff';
            } else if (opinion.includes('[뉴스 전문가]') || opinion.includes('News Agent')) {
                expertType = '뉴스 전문가';
                expertColor = '#dc3545';
            }
            
            // [재무 전문가] 등 태그 제거
            let cleanOpinion = opinion
                .replace(/\[재무 전문가\]\s*/g, '')
                .replace(/\[기술 전문가\]\s*/g, '')
                .replace(/\[뉴스 전문가\]\s*/g, '')
                .replace(/Financial Agent:\s*/gi, '')
                .replace(/Technical Agent:\s*/gi, '')
                .replace(/News Agent:\s*/gi, '')
                .trim();
            
            // 색상 HEX를 RGB로 변환
            const hexToRgb = (hex) => {
                const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
                return result ? {
                    r: parseInt(result[1], 16),
                    g: parseInt(result[2], 16),
                    b: parseInt(result[3], 16)
                } : null;
            };
            
            const rgb = hexToRgb(expertColor);
            const bgColor = rgb ? `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.08)` : 'rgba(128, 128, 128, 0.08)';
            
            html += `
                <div style="
                    background: ${bgColor};
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 10px;
                ">
                    <div style="
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        margin-bottom: 10px;
                        font-weight: 600;
                        color: ${expertColor};
                        font-size: 14px;
                    ">
                        <span>${expertType}</span>
                    </div>
                    <div style="
                        line-height: 1.6;
                        color: #333;
                        font-size: 13px;
                        white-space: pre-wrap;
                    ">${cleanOpinion}</div>
                </div>
            `;
        });
        
        html += `
            </div>
        </div>
        `;
    }
    
    html += `
        <!-- 2. 성과 지표 -->
        <div class="section">
            <div class="section-title">예상 성과 지표</div>
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
            <div class="section-title">추천 종목 종합표</div>
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
            <div class="section-title">종목별 점수 분석</div>
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
            <div class="section-title">포트폴리오 구성</div>
            <div class="chart-container" id="chartContainer">
                <div id="sectorChart" style="height: 400px; width: 100%;"></div>
            </div>
        </div>
        
        <!-- 6. 예상 수익률 차트 -->
        <div class="section">
            <div class="section-title">예상 수익률 추이</div>
            <div class="chart-container">
                <div id="performanceChart" style="height: 400px; width: 100%;"></div>
            </div>
        </div>
        
        <!-- 투자 책임 경고 -->
        <div class="disclaimer" style="background: rgba(255, 243, 205, 0.3); border-radius: 8px; padding: 20px; margin-top: 40px;">
            <p style="color: #495057; font-size: 0.9em; line-height: 1.6; margin: 0;">
                ⚠️ <strong style="color: #f39c12;">투자 유의사항</strong><br>
                본 분석 결과는 AI 알고리즘 기반의 참고 자료이며, 투자 권유나 종목 추천이 아닙니다. 
                과거 데이터와 통계 분석을 기반으로 생성된 정보이므로, 미래 수익을 보장하지 않습니다. 
                모든 투자 결정과 그에 따른 손익은 투자자 본인의 책임입니다.
            </p>
        </div>
        
        <!-- ⭐ PDF 다운로드 버튼을 맨 아래에 추가 -->
        <div style="margin-top: 20px;">
            <button id="downloadPdfBtn" class="btn-primary">
                PDF 다운로드
            </button>
        </div>
    `;
    
    document.getElementById('resultContent').innerHTML = html;
    document.getElementById('resultContent').classList.add('active');
    
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
                        
                        /* ⭐ 전문가 의견 스타일 (PDF용) */
                        .expert-opinion-card {
                            background: #f8f9fa;
                            padding: 12px;
                            border-radius: 6px;
                            margin-bottom: 12px;
                            page-break-inside: avoid;
                        }
                        .expert-header {
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            margin-bottom: 8px;
                            font-weight: 600;
                            font-size: 12px;
                        }
                        .expert-content {
                            line-height: 1.5;
                            color: #333;
                            font-size: 10px;
                            white-space: pre-wrap;
                        }
                    </style>
                </head>
                <body>
                    <h1>AI 투자 포트폴리오 분석 보고서</h1>
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
    
    setTimeout(() => {
        renderSunburstFromConfig(data.chart_config);
        renderPerformanceChart(data);
    }, 300);
}

// ⭐ renderResults 함수 끝
function renderSunburstFromConfig(config) {
    if (!config) {
        createSunburstFromData(data.portfolio_allocation);
        return;
    }
    
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
            textfont: { size: 12, color: 'white', family: 'Pretendard, Arial, sans-serif' },  // ⭐ 흰색
            textinfo: 'label',  // ⭐ 라벨만 표시
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
            height: 400  // ⭐ 390 → 400으로 10px 증가
        };
        
        Plotly.newPlot('sectorChart', chartData, layout, {
            responsive: true,
            displayModeBar: false,
            staticPlot: false
        });
        
    } catch (e) {
        createSunburstFromData(data.portfolio_allocation);
    }
}

// ⭐ Sunburst 차트를 직접 생성하는 함수 (백업용) - 3단계 구조
function createSunburstFromData(portfolio) {
    if (!portfolio || portfolio.length === 0) {
        return;
    }
    
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
    
    // 1. 루트 노드 "포트폴리오" 추가
    const totalPortfolioValue = portfolio.reduce((sum, stock) => sum + ((stock.weight || 0) * 100), 0);
    labels.push('포트폴리오');
    parents.push('');
    values.push(totalPortfolioValue);
    colors.push('#FFFFFF');
    
    // 2. 섹터들 추가 (부모: 포트폴리오)
    Object.entries(sectorMap).forEach(([sector, stocks]) => {
        labels.push(sector);
        parents.push('포트폴리오');
        
        const sectorTotal = stocks.reduce((sum, stock) => sum + ((stock.weight || 0) * 100), 0);
        values.push(sectorTotal);
        colors.push(colorMap[sector] || '#1B8B8B');
    });
    
    // 3. 종목들 추가 (부모: 각 섹터)
    Object.entries(sectorMap).forEach(([sector, stocks]) => {
        stocks.forEach((stock, idx) => {
            const stockName = stock.name || stock.ticker;
            const stockWeight = (stock.weight || 0) * 100;
            
            labels.push(stockName);
            parents.push(sector);
            values.push(stockWeight);
            
            const baseColor = colorMap[sector] || '#1B8B8B';
            const lighterColor = lightenColor(baseColor, idx);
            colors.push(lighterColor);
        });
    });
    
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
        textfont: { size: 12, color: 'white', family: 'Pretendard, Arial, sans-serif' },  // ⭐ 흰색
        textinfo: 'label',  // ⭐ 라벨만 표시
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
        height: 400  // ⭐ 390 → 400으로 10px 증가
    };
    
    try {
        Plotly.newPlot('sectorChart', chartData, layout, {
            responsive: true,
            displayModeBar: false,
            staticPlot: false
        });
    } catch (e) {
        // Error handling
    }
}

// ⭐ 수익률 차트 전용 함수 - Plotly.js로 변경
function renderPerformanceChart(data) {
    const perfContainer = document.getElementById('performanceChart');
    if (!perfContainer) {
        return;
    }
    
    let perfData = null;
    
    if (data.chart_data && data.chart_data.expected_performance) {
        perfData = data.chart_data.expected_performance;
    } else if (data.months && data.portfolio && data.benchmark) {
        perfData = {
            months: data.months,
            portfolio: data.portfolio,
            benchmark: data.benchmark
        };
    }
    
    if (!perfData) {
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
            margin: { l: 60, r: 20, t: 60, b: 80 },
            font: { 
                family: 'Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif', 
                size: 12 
            },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            autosize: true,
            width: null,
            height: 400,
            xaxis: {
                title: {
                    text: '투자 기간',
                    font: { size: 14, color: '#333' },
                    standoff: 15
                },
                showgrid: true,
                gridcolor: 'rgba(0,0,0,0.1)',
                zeroline: false,
                tickfont: { size: 11 },
                tickangle: 0,
                tickmode: 'linear',
                ticklen: 8,
                tickcolor: 'rgba(0,0,0,0.2)'
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
                x: 0.5,
                y: 1.12,
                xanchor: 'center',
                yanchor: 'bottom',
                orientation: 'h',
                bgcolor: 'rgba(255,255,255,0.9)',
                bordercolor: '#ddd',
                borderwidth: 1,
                font: { size: 12 }
            },
            showlegend: true
        };
        
        Plotly.newPlot('performanceChart', chartData, layout, {
            responsive: true,
            displayModeBar: false,
            staticPlot: false
        });
        
    } catch (e) {
        // Error handling
    }
}
