// stock_analysis.js - 단일 종목 분석 시스템

// 종목 목록 로드
async function loadAvailableStocks() {
    try {
        const response = await fetch('/api/stocks');
        const data = await response.json();
        
        const stockSelect = document.getElementById('stockSelect');
        
        if (data.stocks && data.stocks.length > 0) {
            let html = '<option value="">종목을 선택하세요</option>';
            
            // 가나다순 정렬
            const sortedStocks = data.stocks.sort((a, b) => a.name.localeCompare(b.name, 'ko-KR'));
            
            // 단순 목록으로 표시 (시장 구분 없이)
            sortedStocks.forEach(stock => {
                html += `<option value="${stock.ticker}">${stock.name} (${stock.ticker})</option>`;
            });
            
            stockSelect.innerHTML = html;
        }
    } catch (error) {
        console.error('종목 목록 로드 실패:', error);
    }
}

// 모델 목록 로드
async function loadAvailableModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        const modelSelect = document.getElementById('modelSelect');
        modelSelect.innerHTML = data.models.map(model => 
            `<option value="${model}">${getModelDisplayName(model)}</option>`
        ).join('');
    } catch (error) {
        console.error('모델 로드 실패:', error);
    }
}

// 모델 이름 표시
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

// 로딩 컨트롤러
const LoadingController = {
    steps: [
        '기본 정보를 조회하고 있습니다',
        '주가 데이터를 수집하고 있습니다',
        '재무제표를 분석하고 있습니다',
        '기술적 지표를 계산하고 있습니다',
        '뉴스를 검색하고 있습니다',
        '뉴스 감성을 분석하고 있습니다',
        '종합 점수를 산출하고 있습니다',
        '투자 시나리오를 생성하고 있습니다',
        '리스크를 분석하고 있습니다',
        '투자 논리를 구축하고 있습니다',
        '최종 추천을 생성하고 있습니다',
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

// 폼 제출
document.getElementById('analysisForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const ticker = formData.get('ticker');
    
    if (!ticker) {
        alert('종목을 선택해주세요');
        return;
    }
    
    const profile = formData.get('profile');
    const model_name = formData.get('model_name');
    const selectedEngine = formData.get('aiEngine');
    
    // UI 상태 변경
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('loadingState').style.display = 'flex';
    document.getElementById('resultContent').classList.remove('active');
    document.getElementById('analyzeBtn').disabled = true;
    
    // 로딩 애니메이션 시작
    LoadingController.start();

    try {
        let apiEndpoint = '/api/stock/anthropic'; // 기본 엔드포인트

        if (selectedEngine === 'langgraph') {
            apiEndpoint = '/api/stock/langgraph';
        }

        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ticker: ticker,
                profile: profile,
                model_name: model_name
            })
        });
        
        if (!response.ok) {
            throw new Error('분석 실패');
        }
        
        const result = await response.json();
        
        // 로딩 중지
        LoadingController.stop();
        
        // 차트 데이터 로드
        let chartData = null;
        try {
            console.log('📊 차트 데이터 요청 중...');
            const chartDataResponse = await fetch(`/api/chart-data/${ticker}`);
            if (chartDataResponse.ok) {
                chartData = await chartDataResponse.json();
                console.log('✅ 차트 데이터 로드 성공:', chartData);
            } else {
                console.warn('⚠️ 차트 데이터 로드 실패:', chartDataResponse.status);
            }
            
            console.log('🔍 섹터 비교 데이터 요청 중...');
            const sectorResponse = await fetch(`/api/sector-comparison/${ticker}`);
            if (sectorResponse.ok) {
                sectorComparison = await sectorResponse.json();
                console.log('✅ 섹터 비교 데이터 로드 성공:', sectorComparison);
            } else {
                console.warn('⚠️ 섹터 비교 데이터 로드 실패:', sectorResponse.status);
            }
        } catch (error) {
            console.error('❌ 데이터 로드 오류:', error);
        }
        
        // 결과 렌더링
        setTimeout(() => {
            document.getElementById('loadingState').style.display = 'none';
            document.getElementById('resultContent').classList.add('active');
            renderResults(result, chartData, sectorComparison);
        }, 500);
        
    } catch (error) {
        console.error('분석 오류:', error);
        alert('분석 중 오류가 발생했습니다: ' + error.message);
        
        document.getElementById('loadingState').style.display = 'none';
        document.getElementById('emptyState').style.display = 'block';
    } finally {
        document.getElementById('analyzeBtn').disabled = false;
        LoadingController.stop();
    }
});

// 결과 렌더링
function renderResults(data, chartData, sectorComparison) {
    // 콘솔에 전체 데이터 출력 (디버깅용)
    console.log('분석 결과 데이터:', data);
    console.log('차트 데이터:', chartData);
    console.log('섹터 비교:', sectorComparison);
    console.log('투자 추천 전체:', data.recommendation);
    console.log('목표가 범위:', data.recommendation?.target_price_range);
    console.log('시장 현황:', data.market_snapshot);
    console.log('시나리오:', data.scenarios_1y);
    console.log('현재가:', data.market_snapshot?.current_price);
    console.log('목표가:', data.recommendation?.target_price_range);
    console.log('재무 데이터:', {
        revenue: data.financial_summary?.revenue,
        op_income: data.financial_summary?.op_income,
        net_income: data.financial_summary?.net_income
    });
    
    const basic = data.basic_info || {};
    const market = data.market_snapshot || {};
    const financial = data.financial_summary || {};
    const scores = data.quality_scores || {};
    const technical = data.technical_analysis || {};
    const news = data.news_and_momentum || {};
    const scenarios = data.scenarios_1y || {};
    const risks = data.risks || {};
    const thesis = data.investment_thesis || {};
    const recommendation = data.recommendation || {};
    
    // 투자 의견 배지 색상 결정
    const getRatingBadge = (rating) => {
        const ratingUpper = (rating || '').toUpperCase();
        let bgColor, textColor, text;
        
        if (ratingUpper.includes('강력 매수') || ratingUpper.includes('STRONG BUY')) {
            bgColor = '#059669';
            textColor = '#ffffff';
            text = '강력 매수';
        } else if (ratingUpper.includes('매수') || ratingUpper.includes('BUY')) {
            bgColor = '#10b981';
            textColor = '#ffffff';
            text = '매수';
        } else if (ratingUpper.includes('보유') || ratingUpper.includes('HOLD')) {
            bgColor = '#f59e0b';
            textColor = '#ffffff';
            text = '보유';
        } else if (ratingUpper.includes('매도') || ratingUpper.includes('SELL')) {
            bgColor = '#ef4444';
            textColor = '#ffffff';
            text = '매도';
        } else {
            bgColor = '#6b7280';
            textColor = '#ffffff';
            text = rating || 'N/A';
        }
        
        return `<span style="
            display: inline-block;
            background: ${bgColor};
            color: ${textColor};
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.75em;
            font-weight: 600;
            margin-left: 10px;
            vertical-align: middle;
        ">${text}</span>`;
    };
    
    let html = `
        <!-- 헤더 섹션 -->
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px;
            border-radius: 15px;
            margin-bottom: 30px;
            color: white;
        " class="stock-header">
            <div style="font-size: 2.2em; font-weight: 700; margin-bottom: 10px;">
                ${basic.name_kr || '종목명'}
                ${getRatingBadge(recommendation.rating)}
            </div>
            <div style="font-size: 1.1em; opacity: 0.95; margin-bottom: 15px;">
                ${basic.ticker || '-'} | ${basic.market || '-'} | ${basic.industry || '-'}
            </div>
            <div style="font-size: 1.05em; line-height: 1.7; opacity: 0.9; margin-top: 20px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.2);">
                ${basic.summary_sentence || ''}
            </div>
        </div>
        
        <!-- 투자 추천 -->
        <div class="section">
            <div class="section-title">투자 추천</div>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">목표주가</div>
                    <div class="metric-value target-price-value" style="font-size: 1.5em;">${recommendation.target_price_range || 'N/A'}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">투자 기간</div>
                    <div class="metric-value" style="font-size: 1.5em;">${recommendation.time_horizon_months || 12}개월</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">신뢰도</div>
                    <div class="metric-value" style="font-size: 1.5em;">${getConfidenceText(recommendation.confidence_level) || 'N/A'}</div>
                </div>
            </div>
            <div class="summary-box" style="margin-top: 20px;">
                <p><strong>손절 힌트:</strong> ${recommendation.stop_loss_hint || 'N/A'}</p>
                <p style="margin-top: 10px;">${recommendation.recommendation_comment || '추천 코멘트 없음'}</p>
            </div>
        </div>
        
        <!-- 종합 점수 -->
        <div class="section" style="margin-top: 80px;">
            <div class="section-title">종합 평가 점수</div>
            <div class="metrics-grid four-columns">
                <div class="metric-card">
                    <div class="metric-label">재무 점수</div>
                    <div class="metric-value">${scores.financial_score || 0}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${scores.financial_score || 0}%"></div>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">기술적 점수</div>
                    <div class="metric-value">${scores.technical_score || 0}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${scores.technical_score || 0}%"></div>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">뉴스 점수</div>
                    <div class="metric-value">${scores.news_score || 0}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${scores.news_score || 0}%"></div>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">종합 점수</div>
                    <div class="metric-value" style="color: #667eea;">${scores.overall_score || 0}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${scores.overall_score || 0}%"></div>
                    </div>
                </div>
            </div>
            <div class="summary-box" style="margin-top: 20px;">
                <p>${scores.score_comment || '점수 분석 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 시장 현황 -->
        <div class="section">
            <div class="section-title">시장 현황</div>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">현재가</div>
                    <div class="metric-value">₩${formatNumber(market.current_price || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">1일 변동</div>
                    <div class="metric-value" style="color: ${(market.price_change_1d || 0) >= 0 ? '#10b981' : '#ef4444'}">
                        ${formatPercent(market.price_change_1d || 0)}
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">1개월 수익률</div>
                    <div class="metric-value">${formatPercent(market.return_1m || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">3개월 수익률</div>
                    <div class="metric-value">${formatPercent(market.return_3m || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">6개월 수익률</div>
                    <div class="metric-value">${formatPercent(market.return_6m || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">변동성 (20일)</div>
                    <div class="metric-value">${formatPercent(market.volatility_20d || 0)}</div>
                </div>
            </div>
            <div class="summary-box" style="margin-top: 20px;">
                <p>${market.relative_to_market || '시장 대비 수익률 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 주가 차트 -->
        <div class="section">
            <div class="section-title">주가 추이 (6개월)</div>
            <div id="priceChart" style="height: 400px; width: 100%;"></div>
        </div>
        
        <!-- 기술적 지표 상태 테이블 -->
        <div class="section">
            <div class="section-title">기술적 지표 상태</div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; font-size: 0.9em;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">지표</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">값</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">신호</th>
                        </tr>
                    </thead>
                    <tbody id="technicalIndicatorsTableBody">
                        <!-- JavaScript로 동적 생성 -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- 기술적 분석 -->
        <div class="section">
            <div class="section-title">기술적 분석</div>
            <!-- 연결 테스트 -->
            <div class="metrics-grid four-columns">
                <div class="metric-card">
                    <div class="metric-label">추세</div>
                    <div class="metric-value">${getTrendText(technical.trend)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">RSI (14일)</div>
                    <div class="metric-value">${(technical.rsi14 || 50).toFixed(1)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">모멘텀 (20일)</div>
                    <div class="metric-value">${formatPercent(technical.momentum_20d || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">변동성</div>
                    <div class="metric-value">${getVolatilityText(technical.volatility_20d_level)}</div>
                </div>
            </div>
            <div class="summary-box" style="margin-top: 20px;">
                <p><strong>지지 구간:</strong> ${technical.support_resistance?.support_zone || 'N/A'}</p>
                <p><strong>저항 구간:</strong> ${technical.support_resistance?.resistance_zone || 'N/A'}</p>
                <p style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd;">
                    ${technical.technical_comment || '기술적 분석 정보 없음'}
                </p>
            </div>
        </div>
        
        <!-- 재무 실적 -->
        <div class="section">
            <div class="section-title">재무 실적 (${financial.latest_period || 'N/A'})</div>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">매출액</div>
                    <div class="metric-value">${formatKoreanWon(financial.revenue || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">영업이익</div>
                    <div class="metric-value">${formatKoreanWon(financial.op_income || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">당기순이익</div>
                    <div class="metric-value">${formatKoreanWon(financial.net_income || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">영업이익률</div>
                    <div class="metric-value">${formatPercent(financial.opm || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">ROE</div>
                    <div class="metric-value">${formatPercent(financial.roe || 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">부채비율</div>
                    <div class="metric-value">${formatPercent(financial.debt_ratio || 0)}</div>
                </div>
            </div>
            <div class="summary-box" style="margin-top: 20px;">
                <p>${financial.financial_comment || '재무 분석 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 재무 성과 차트 -->
        <div class="section">
            <div class="section-title">재무 성과 추이 (4분기)</div>
            <div id="financialChart" style="height: 400px; width: 100%;"></div>
        </div>
        
        <!-- 재무 비율 트렌드 표 -->
        <div class="section">
            <div class="section-title">재무 비율 트렌드</div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; font-size: 0.9em;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">기간</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">매출</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">영업이익률</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">ROE</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">부채비율</th>
                        </tr>
                    </thead>
                    <tbody id="financialTrendTableBody">
                        <!-- JavaScript로 동적 생성 -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- 밸류에이션 멀티플 비교표 -->
        <div class="section" id="valuationComparisonSection">
            <div class="section-title">밸류에이션 멀티플 비교 (섹터 내)</div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; font-size: 0.9em;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">종목</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">PER</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">PBR</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #dee2e6;">EV/EBITDA</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #dee2e6;">비고</th>
                        </tr>
                    </thead>
                    <tbody id="valuationComparisonTableBody">
                        <!-- JavaScript로 동적 생성 -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- 시나리오 비교 표 -->
        <div class="section">
            <div class="section-title">시나리오 비교</div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">시나리오</th>
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">예상 수익률</th>
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">설명</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 12px;"><strong style="color: #059669;">강세</strong></td>
                            <td style="padding: 12px; color: #059669; font-weight: 600;">${scenarios.bull_case?.expected_return_range || 'N/A'}</td>
                            <td style="padding: 12px; font-size: 0.9em;">${scenarios.bull_case?.description || '-'}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 12px;"><strong style="color: #f59e0b;">기본</strong></td>
                            <td style="padding: 12px; color: #f59e0b; font-weight: 600;">${scenarios.base_case?.expected_return_range || 'N/A'}</td>
                            <td style="padding: 12px; font-size: 0.9em;">${scenarios.base_case?.description || '-'}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px;"><strong style="color: #ef4444;">약세</strong></td>
                            <td style="padding: 12px; color: #ef4444; font-weight: 600;">${scenarios.bear_case?.expected_return_range || 'N/A'}</td>
                            <td style="padding: 12px; font-size: 0.9em;">${scenarios.bear_case?.description || '-'}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="summary-box" style="margin-top: 15px;">
                <p>${scenarios.scenario_comment || '시나리오 분석 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 뉴스 & 모멘텀 -->
        <div class="section">
            <div class="section-title">뉴스 & 모멘텀</div>
            <div class="summary-box" style="margin-bottom: 15px;">
                <p><strong>감성:</strong> ${getSentimentText(news.sentiment)}</p>
                <p><strong>섹터 트렌드:</strong> ${news.sector_trend || 'N/A'}</p>
            </div>
    `;
    
    // 뉴스 하이라이트
    if (news.recent_news_highlights && news.recent_news_highlights.length > 0) {
        html += '<div style="margin-top: 20px;">';
        news.recent_news_highlights.forEach(item => {
            html += `
                <div class="summary-box" style="margin-bottom: 10px; background: #f8f9fa;">
                    <h4 style="color: #667eea; margin-bottom: 8px;">${item.title}</h4>
                    <p style="font-size: 0.95em;">${item.summary}</p>
                </div>
            `;
        });
        html += '</div>';
    }
    
    html += `
            <div class="summary-box" style="margin-top: 15px;">
                <p>${news.news_comment || '뉴스 분석 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 리스크 -->
        <div class="section">
            <div class="section-title">주요 리스크</div>
    `;
    
    if (risks.major_risks && risks.major_risks.length > 0) {
        risks.major_risks.forEach(risk => {
            const severityColor = {
                'high': '#fef2f2',
                'medium': '#fffbeb',
                'low': '#f0f9ff'
            }[risk.severity] || '#f9fafb';
            
            const borderColor = {
                'high': '#ef4444',
                'medium': '#f59e0b',
                'low': '#3b82f6'
            }[risk.severity] || '#9ca3af';
            
            html += `
                <div class="summary-box" style="background: ${severityColor}; margin-bottom: 10px;">
                    <h4 style="margin-bottom: 8px;">${risk.title} <span style="font-size: 0.8em; color: #666;">[${getSeverityText(risk.severity)}]</span></h4>
                    <p>${risk.description}</p>
                </div>
            `;
        });
    }
    
    html += `
        </div>
        
        <!-- 투자 논리 -->
        <div class="section">
            <div class="section-title">투자 논리</div>
            <div class="summary-box" style="margin-bottom: 15px;">
                <h4 style="margin-bottom: 10px;">핵심 투자 포인트</h4>
                <ul style="padding-left: 20px;">
    `;
    
    if (thesis.key_points && thesis.key_points.length > 0) {
        thesis.key_points.forEach(point => {
            html += `<li style="margin-bottom: 8px;">${point}</li>`;
        });
    }
    
    html += `
                </ul>
            </div>
            <div class="summary-box">
                <p><strong>종합 의견:</strong></p>
                <p style="margin-top: 10px;">${thesis.long_form_summary || '투자 논리 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 면책 조항 -->
        <div class="disclaimer">
            <p><strong>⚠️ 투자 유의사항</strong></p>
            <p style="margin-top: 10px;">본 분석은 AI 기반 데이터 분석 시스템에 의해 생성된 참고 자료입니다. 투자 결정에 따른 책임은 투자자 본인에게 있으며, 반드시 추가적인 리서치를 수행하시기 바랍니다.</p>
        </div>
        
        <!-- PDF 다운로드 버튼 (하단) -->
        <div style="margin-top: 20px;">
            <button id="downloadPdfBtn" class="btn-primary">
                PDF 다운로드
            </button>
        </div>
        
        <!-- 디버그 정보 (개발용) -->
        <details style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;">
            <summary style="cursor: pointer; font-weight: 600; color: #667eea;">상세 데이터 확인 (클릭)</summary>
            <pre style="margin-top: 10px; padding: 10px; background: white; border-radius: 4px; overflow-x: auto; font-size: 0.85em;">${JSON.stringify(data, null, 2)}</pre>
        </details>
    `;
    
    document.getElementById('resultContent').innerHTML = html;
    document.getElementById('resultContent').classList.add('active');
    
    // 차트 렌더링 (디버깅 로그 추가)
    console.log('🎨 차트 렌더링 시작');
    console.log('📊 차트 데이터:', chartData);
    console.log('🎯 목표가:', recommendation.target_price_range);
    console.log('💰 현재가:', market.current_price);
    
    setTimeout(() => {
        try {
            renderCharts(chartData, recommendation.target_price_range, market.current_price);
            fillFinancialTrendTable(chartData);
            fillValuationComparisonTable(sectorComparison);
            fillTechnicalIndicatorTable(chartData, technical);
            console.log('✅ 차트 렌더링 완료');
        } catch (error) {
            console.error('❌ 차트 렌더링 오류:', error);
        }
    }, 100);
    
    // PDF 다운로드 이벤트 (중복 방지)
    const downloadBtn = document.getElementById('downloadPdfBtn');
    const newBtn = downloadBtn.cloneNode(true);
    downloadBtn.parentNode.replaceChild(newBtn, downloadBtn);
    
    newBtn.addEventListener('click', async () => {
        newBtn.disabled = true;
        newBtn.textContent = 'PDF 생성 중...';
        
        try {
            // 1. 결과 HTML을 복사본으로 만들기
            const resultContentClone = document.getElementById('resultContent').cloneNode(true);
            
            // 2. 차트를 이미지로 변환
            const priceChartDiv = document.getElementById('priceChart');
            const financialChartDiv = document.getElementById('financialChart');
            
            // 복사본에서 차트 div 찾기
            const clonedPriceChart = resultContentClone.querySelector('#priceChart');
            const clonedFinancialChart = resultContentClone.querySelector('#financialChart');
            
            // 주가 차트 이미지로 교체
            if (priceChartDiv && priceChartDiv.querySelector('.plotly') && clonedPriceChart) {
                try {
                    const imgData = await Plotly.toImage(priceChartDiv, {
                        format: 'png',
                        width: 800,
                        height: 400
                    });
                    const img = document.createElement('img');
                    img.src = imgData;
                    img.style.cssText = 'width: 100%; max-width: 800px; height: auto; display: block; margin: 20px auto;';
                    clonedPriceChart.parentNode.replaceChild(img, clonedPriceChart);
                    console.log('✅ 주가 차트 이미지 변환 완료');
                } catch (e) {
                    console.warn('⚠️ 주가 차트 변환 실패:', e);
                    // 실패 시 차트 div 제거
                    if (clonedPriceChart.parentNode) {
                        clonedPriceChart.parentNode.removeChild(clonedPriceChart);
                    }
                }
            }
            
            // 재무 차트 이미지로 교체
            if (financialChartDiv && financialChartDiv.querySelector('.plotly') && clonedFinancialChart) {
                try {
                    const imgData = await Plotly.toImage(financialChartDiv, {
                        format: 'png',
                        width: 800,
                        height: 400
                    });
                    const img = document.createElement('img');
                    img.src = imgData;
                    img.style.cssText = 'width: 100%; max-width: 800px; height: auto; display: block; margin: 20px auto;';
                    clonedFinancialChart.parentNode.replaceChild(img, clonedFinancialChart);
                    console.log('✅ 재무 차트 이미지 변환 완료');
                } catch (e) {
                    console.warn('⚠️ 재무 차트 변환 실패:', e);
                    // 실패 시 차트 div 제거
                    if (clonedFinancialChart.parentNode) {
                        clonedFinancialChart.parentNode.removeChild(clonedFinancialChart);
                    }
                }
            }
            
            // 3. 기존 CSS 파일 로드
            const cssResponse = await fetch('/static/stock_analysis.css');
            const cssContent = await cssResponse.text();
            
            // 4. PDF 전용 스타일 조정
            const targetPriceElements = resultContentClone.querySelectorAll('.target-price-value');
            targetPriceElements.forEach(el => {
                el.style.setProperty('font-size', '0.8em', 'important');
            });
            
            // 5. 변환된 HTML 가져오기
            const resultHtml = resultContentClone.innerHTML;
            
            // 6. 화면과 동일한 HTML 구조 + CSS 포함
            const fullHtml = `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        /* 화면과 동일한 CSS */
                        ${cssContent}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div style="text-align: center; margin-bottom: 30px; padding-top: 20px;">
                            <h1 style="color: #667eea; font-size: 2em; margin-bottom: 10px;">AI 단일 종목 분석 보고서</h1>
                            <p style="color: #666; font-size: 1em;">
                                생성일시: ${new Date().toLocaleString('ko-KR')}
                            </p>
                        </div>
                        <div class="panel result-panel">
                            ${resultHtml}
                        </div>
                    </div>
                </body>
                </html>
            `;
            
            const response = await fetch('/api/stock/download-pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ html: fullHtml })
            });
            
            if (!response.ok) throw new Error('PDF 생성 실패');
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `stock_analysis_${basic.ticker}_${new Date().getTime()}.pdf`;
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
}

// AI 엔진 선택 이벤트 리스너 추가
document.addEventListener('DOMContentLoaded', function() {
    const engineOptions = document.querySelectorAll('input[name="aiEngine"]');

    engineOptions.forEach(option => {
        option.addEventListener('change', () => {
            console.log(`선택된 AI 엔진: ${option.value}`);
        });
    });
});

// 유틸리티 함수들
function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(Math.round(num));
}

function formatPercent(num) {
    return (num * 100).toFixed(1) + '%';
}

function formatKoreanWon(num) {
    const trillion = num / 1e12;
    const billion = (num % 1e12) / 1e8;
    
    if (trillion >= 1) {
        return `${trillion.toFixed(1)}조원`;
    } else if (billion >= 1) {
        return `${billion.toFixed(1)}억원`;
    } else {
        return formatNumber(num) + '원';
    }
}

function getTrendEmoji(trend) {
    return ''
}

function getTrendText(trend) {
    const text = {
        'uptrend': '상승 추세',
        'downtrend': '하락 추세',
        'sideways': '횡보'
    };
    return text[trend] || '알 수 없음';
}

function getSentimentEmoji(sentiment) {
    return '';
}

function getSentimentText(sentiment) {
    const text = {
        'positive': '긍정적',
        'neutral': '중립',
        'negative': '부정적'
    };
    return text[sentiment] || '중립';
}

function getVolatilityText(level) {
    const text = {
        'low': '낮음',
        'medium': '보통',
        'high': '높음'
    };
    return text[level] || '보통';
}

function getSeverityText(severity) {
    const text = {
        'high': '높음',
        'medium': '중간',
        'low': '낮음'
    };
    return text[severity] || '중간';
}

function getConfidenceText(level) {
    const text = {
        'high': '높음',
        'medium': '중간',
        'low': '낮음'
    };
    return text[level] || '중간';
}

function getRecommendationColor(rating) {
    const colors = {
        'BUY': 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        'HOLD': 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        'SELL': 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
    };
    return colors[rating] || 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
}

// 기술적 지표 헬퍼 함수들
function getRsiSignal(rsi) {
    if (!rsi) return '중립';
    if (rsi > 70) return '과매수';
    if (rsi < 30) return '과매도';
    if (rsi >= 50) return '강세';
    return '약세';
}

function getRsiSignalColor(rsi) {
    if (!rsi) return '#666';
    if (rsi > 70) return '#ef4444';
    if (rsi < 30) return '#10b981';
    if (rsi >= 50) return '#059669';
    return '#f59e0b';
}

function getRsiSignal(rsi) {
    if (!rsi) return '데이터 없음';
    if (rsi > 70) return '과매수 (매도 고려)';
    if (rsi < 30) return '과매도 (매수 고려)';
    if (rsi >= 50) return '강세';
    return '약세';
}

function getMaSignal(ma20, ma60, currentPrice) {
    if (!ma20 || !ma60 || !currentPrice) return '데이터 없음';
    if (ma20 > ma60) return '골든크로스 (상향)';
    if (ma20 < ma60) return '데드크로스 (하향)';
    return '중립';
}

function getMaSignalColor(ma20, ma60, currentPrice) {
    if (!ma20 || !ma60) return '#666';
    if (ma20 > ma60) return '#10b981';
    if (ma20 < ma60) return '#ef4444';
    return '#666';
}

function getMomentumSignal(momentum) {
    if (!momentum) return '중립';
    if (momentum > 0.05) return '강한 상승 모멘텀';
    if (momentum > 0) return '상승 모멘텀';
    if (momentum > -0.05) return '하락 모멘텀';
    return '강한 하락 모멘텀';
}

function getMomentumSignalColor(momentum) {
    if (!momentum) return '#666';
    if (momentum > 0.05) return '#10b981';
    if (momentum > 0) return '#059669';
    if (momentum > -0.05) return '#f59e0b';
    return '#ef4444';
}

function getVolatilitySignalColor(level) {
    const colors = {
        'low': '#10b981',
        'medium': '#f59e0b',
        'high': '#ef4444'
    };
    return colors[level] || '#666';
}

function getVolatilityText(level) {
    const texts = {
        'low': '낮음',
        'medium': '보통',
        'high': '높음'
    };
    return texts[level] || '데이터 없음';
}

// 재무 비율 트렌드 테이블 채우기
function fillFinancialTrendTable(chartData) {
    const tbody = document.getElementById('financialTrendTableBody');
    if (!tbody || !chartData || !chartData.financials || chartData.financials.length === 0) {
        return;
    }
    
    let html = '';
    chartData.financials.forEach((item, index) => {
        const prevItem = index > 0 ? chartData.financials[index - 1] : null;
        
        // 영업이익률 계산
        const opm = item.revenue > 0 ? (item.operating_income / item.revenue * 100) : 0;
        
        // ROE와 부채비율 표시
        const roeText = item.roe ? (item.roe * 100).toFixed(1) + '%' : '-';
        const debtRatioText = item.debt_ratio ? (item.debt_ratio * 100).toFixed(1) + '%' : '-';
        
        html += `
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 10px;"><strong>${item.period}</strong></td>
                <td style="padding: 10px; text-align: right;">${formatKoreanWon(item.revenue || 0)}</td>
                <td style="padding: 10px; text-align: right;">${opm.toFixed(1)}%</td>
                <td style="padding: 10px; text-align: right;">${roeText}</td>
                <td style="padding: 10px; text-align: right;">${debtRatioText}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// 기술적 지표 테이블 채우기 (차트 데이터로부터 직접 계산)
function fillTechnicalIndicatorTable(chartData, technical) {
    const tbody = document.getElementById('technicalIndicatorsTableBody');
    if (!tbody) {
        console.error('technicalIndicatorsTableBody element not found');
        return;
    }

    if (!chartData || !chartData.prices || chartData.prices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 20px;">데이터 없음</td></tr>';
        return;
    }

    const prices = chartData.prices;
    const currentPrice = prices[prices.length - 1].close;
    
    // MA20, MA60 계산
    let ma20 = null, ma60 = null;
    if (prices.length >= 20) {
        const sum20 = prices.slice(-20).reduce((acc, p) => acc + p.close, 0);
        ma20 = sum20 / 20;
    }
    if (prices.length >= 60) {
        const sum60 = prices.slice(-60).reduce((acc, p) => acc + p.close, 0);
        ma60 = sum60 / 60;
    }

    // 모멘텀 계산 (20일 변화율)
    let momentum20 = null;
    if (prices.length >= 21) {
        const price20DaysAgo = prices[prices.length - 21].close;
        momentum20 = (currentPrice - price20DaysAgo) / price20DaysAgo;
    }

    // 변동성 계산 (20일 표준편차)
    let volatility20 = null;
    if (prices.length >= 20) {
        const last20Prices = prices.slice(-20).map(p => p.close);
        const mean = last20Prices.reduce((a, b) => a + b, 0) / 20;
        const variance = last20Prices.reduce((acc, p) => acc + Math.pow(p - mean, 2), 0) / 20;
        volatility20 = Math.sqrt(variance) / mean;
    }

    // RSI는 backend에서 가져온 값 사용
    const rsi = technical && technical.rsi14 ? technical.rsi14 : null;

    // 테이블 행 생성
    let rows = '';

    // RSI
    rows += `
        <tr style="border-bottom: 1px solid #dee2e6;">
            <td style="padding: 10px;"><strong>RSI(14)</strong></td>
            <td style="padding: 10px; text-align: right;">${rsi !== null ? rsi.toFixed(1) : 'N/A'}</td>
            <td style="padding: 10px; ${getRsiSignalColor(rsi) ? 'color: ' + getRsiSignalColor(rsi) + ';' : ''}">${getRsiSignal(rsi)}</td>
        </tr>
    `;

    // 이동평균
    rows += `
        <tr style="border-bottom: 1px solid #dee2e6;">
            <td style="padding: 10px;"><strong>이동평균</strong></td>
            <td style="padding: 10px; text-align: right;">
                MA20: ${ma20 !== null ? formatNumber(ma20) : 'N/A'}<br>
                MA60: ${ma60 !== null ? formatNumber(ma60) : 'N/A'}
            </td>
            <td style="padding: 10px; ${getMaSignalColor(ma20, ma60, currentPrice) ? 'color: ' + getMaSignalColor(ma20, ma60, currentPrice) + ';' : ''}">${getMaSignal(ma20, ma60, currentPrice)}</td>
        </tr>
    `;

    // 모멘텀
    rows += `
        <tr style="border-bottom: 1px solid #dee2e6;">
            <td style="padding: 10px;"><strong>모멘텀(20일)</strong></td>
            <td style="padding: 10px; text-align: right;">${momentum20 !== null ? formatPercent(momentum20) : 'N/A'}</td>
            <td style="padding: 10px; ${getMomentumSignalColor(momentum20) ? 'color: ' + getMomentumSignalColor(momentum20) + ';' : ''}">${getMomentumSignal(momentum20)}</td>
        </tr>
    `;

    // 변동성
    const volatilityLevel = getVolatilityLevel(volatility20);
    rows += `
        <tr>
            <td style="padding: 10px;"><strong>변동성(20일)</strong></td>
            <td style="padding: 10px; text-align: right;">${volatility20 !== null ? formatPercent(volatility20) : 'N/A'}</td>
            <td style="padding: 10px; ${getVolatilitySignalColor(volatilityLevel) ? 'color: ' + getVolatilitySignalColor(volatilityLevel) + ';' : ''}">${getVolatilityText(volatilityLevel)}</td>
        </tr>
    `;

    tbody.innerHTML = rows;
}

// 변동성 레벨 계산
function getVolatilityLevel(volatility) {
    if (volatility === null) return null;
    if (volatility < 0.02) return 'low';
    if (volatility < 0.04) return 'medium';
    return 'high';
}

// 밸류에이션 비교 테이블 채우기
function fillValuationComparisonTable(sectorComparison) {
    const section = document.getElementById('valuationComparisonSection');
    const tbody = document.getElementById('valuationComparisonTableBody');
    
    if (!tbody) return;
    
    if (!sectorComparison || !sectorComparison.comparisons || sectorComparison.comparisons.length === 0) {
        section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    let html = '';
    sectorComparison.comparisons.forEach(comp => {
        const isTarget = comp.is_target;
        const rowStyle = isTarget ? 'background: #f0f9ff; font-weight: 600;' : '';
        const remarkText = isTarget ? '<span style="color: #667eea; font-weight: 600;">분석 대상</span>' : '<span style="color: #666;">경쟁사</span>';
        
        html += `
            <tr style="border-bottom: 1px solid #dee2e6; ${rowStyle}">
                <td style="padding: 10px;">${comp.name || comp.ticker}</td>
                <td style="padding: 10px; text-align: right;">${comp.per ? comp.per.toFixed(1) + 'x' : '-'}</td>
                <td style="padding: 10px; text-align: right;">${comp.pbr ? comp.pbr.toFixed(2) + 'x' : '-'}</td>
                <td style="padding: 10px; text-align: right;">${comp.ev_ebitda ? comp.ev_ebitda.toFixed(1) + 'x' : '-'}</td>
                <td style="padding: 10px; text-align: center;">${remarkText}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// 차트 렌더링 함수
function renderCharts(chartData, targetPrice, currentPrice) {
    console.log('🎨 renderCharts 호출됨');
    console.log('  chartData:', chartData);
    console.log('  targetPrice:', targetPrice);
    console.log('  currentPrice:', currentPrice);
    
    // 1. 주가 차트
    if (chartData && chartData.prices && chartData.prices.length > 0) {
        console.log('📈 주가 차트 데이터 있음:', chartData.prices.length, '개');
        
        const dates = chartData.prices.map(p => p.date);
        const prices = chartData.prices.map(p => p.close);
        
        // 20일 이동평균
        const ma20 = [];
        for (let i = 0; i < prices.length; i++) {
            if (i < 19) {
                ma20.push(null);
            } else {
                const sum = prices.slice(i - 19, i + 1).reduce((a, b) => a + b, 0);
                ma20.push(sum / 20);
            }
        }
        
        // 60일 이동평균
        const ma60 = [];
        for (let i = 0; i < prices.length; i++) {
            if (i < 59) {
                ma60.push(null);
            } else {
                const sum = prices.slice(i - 59, i + 1).reduce((a, b) => a + b, 0);
                ma60.push(sum / 60);
            }
        }
        
        const priceTrace = {
            x: dates,
            y: prices,
            type: 'scatter',
            mode: 'lines',
            name: '종가',
            line: { color: '#6366F1', width: 2.5 }
        };
        
        const ma20Trace = {
            x: dates,
            y: ma20,
            type: 'scatter',
            mode: 'lines',
            name: '20일 이평선',
            line: { color: '#818CF8', width: 1.5, dash: 'dash' }
        };
        
        const ma60Trace = {
            x: dates,
            y: ma60,
            type: 'scatter',
            mode: 'lines',
            name: '60일 이평선',
            line: { color: '#C7D2FE', width: 1.5, dash: 'dash' }
        };
        
        const traces = [priceTrace, ma20Trace, ma60Trace];
        
        // 목표가 범위 표시 (있는 경우)
        if (targetPrice && typeof targetPrice === 'string') {
            const match = targetPrice.match(/(\d{1,3}(,\d{3})*(\.\d+)?)/g);
            if (match && match.length >= 1) {
                const targetValue = parseFloat(match[0].replace(/,/g, ''));
                traces.push({
                    x: dates,
                    y: Array(dates.length).fill(targetValue),
                    type: 'scatter',
                    mode: 'lines',
                    name: '목표가',
                    line: { color: '#F59E0B', width: 2.5, dash: 'dot' }
                });
            }
        }
        
        const priceLayout = {
            title: '',
            xaxis: { title: '날짜' },
            yaxis: { title: '가격 (원)' },
            showlegend: true,
            legend: { x: 0, y: 1 },
            margin: { l: 50, r: 30, t: 30, b: 50 }
        };
        
        Plotly.newPlot('priceChart', traces, priceLayout, { responsive: true });
        console.log('✅ 주가 차트 렌더링 완료');
    } else {
        console.warn('⚠️ 주가 차트 데이터 없음');
    }
    
    // 2. 재무 차트
    if (chartData && chartData.financials && chartData.financials.length > 0) {
        console.log('📊 재무 차트 데이터 있음:', chartData.financials.length, '개');
        const periods = chartData.financials.map(f => f.period);
        const revenues = chartData.financials.map(f => f.revenue ? f.revenue / 1e8 : 0);
        const opIncomes = chartData.financials.map(f => f.operating_income ? f.operating_income / 1e8 : 0);
        const netIncomes = chartData.financials.map(f => f.net_income ? f.net_income / 1e8 : 0);
        
        const revenueTrace = {
            x: periods,
            y: revenues,
            type: 'bar',
            name: '매출액',
            marker: { color: '#A5B4FC' }
        };
        
        const opIncomeTrace = {
            x: periods,
            y: opIncomes,
            type: 'bar',
            name: '영업이익',
            marker: { color: '#6366F1' }
        };
        
        const netIncomeTrace = {
            x: periods,
            y: netIncomes,
            type: 'bar',
            name: '순이익',
            marker: { color: '#CBD5E1' }
        };
        
        const financialLayout = {
            title: '',
            xaxis: { title: '분기' },
            yaxis: { title: '금액 (억원)' },
            barmode: 'group',
            showlegend: true,
            legend: { x: 0, y: 1 },
            margin: { l: 50, r: 30, t: 30, b: 50 }
        };
        
        Plotly.newPlot('financialChart', [revenueTrace, opIncomeTrace, netIncomeTrace], financialLayout, { responsive: true });
        console.log('✅ 재무 차트 렌더링 완료');
    } else {
        console.warn('⚠️ 재무 차트 데이터 없음');
    }
}

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    loadAvailableStocks();
    loadAvailableModels();
});
