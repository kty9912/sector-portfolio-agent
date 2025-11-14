// stock_analysis.js - 단일 종목 분석 시스템

// 종목 목록 로드
async function loadAvailableStocks() {
    try {
        const response = await fetch('/api/stocks');
        const data = await response.json();
        
        const stockSelect = document.getElementById('stockSelect');
        
        if (data.stocks && data.stocks.length > 0) {
            let html = '<option value="">종목을 선택하세요</option>';
            
            // 단순 목록으로 표시 (시장 구분 없이)
            data.stocks.forEach(stock => {
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
    
    // UI 상태 변경
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('loadingState').style.display = 'flex';
    document.getElementById('resultContent').classList.remove('active');
    document.getElementById('analyzeBtn').disabled = true;
    
    // 로딩 시작
    LoadingController.start();
    
    try {
        const response = await fetch('/api/analyze', {
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
        
        // 결과 렌더링
        setTimeout(() => {
            document.getElementById('loadingState').style.display = 'none';
            document.getElementById('resultContent').classList.add('active');
            renderResults(result);
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
function renderResults(data) {
    // 콘솔에 전체 데이터 출력 (디버깅용)
    console.log('📊 분석 결과 데이터:', data);
    console.log('💰 현재가:', data.market_snapshot?.current_price);
    console.log('🎯 목표가:', data.recommendation?.target_price_range);
    console.log('📈 재무 데이터:', {
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
    
    let html = `
        <!-- 기본 정보 -->
        <div class="section">
            <div class="section-title">📊 기본 정보</div>
            <div class="summary-box">
                <h3 style="margin-bottom: 15px; font-size: 1.5em;">${basic.name_kr || '종목명'}</h3>
                <p><strong>티커:</strong> ${basic.ticker || '-'}</p>
                <p><strong>시장:</strong> ${basic.market || '-'}</p>
                <p><strong>업종:</strong> ${basic.industry || '-'}</p>
                <p><strong>시가총액:</strong> ${basic.market_cap_level || '-'}</p>
                <p style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd;">
                    ${basic.summary_sentence || ''}
                </p>
            </div>
        </div>
        
        <!-- 투자 추천 -->
        <div class="section">
            <div class="section-title">🎯 투자 추천</div>
            <div class="summary-box" style="background: #ffffff; padding: 30px;">
                <h3 style="font-size: 2em; margin-bottom: 20px; text-align: center;">
                    투자의견: <strong>${recommendation.rating || 'N/A'}</strong>
                </h3>
                <div class="metrics-grid" style="margin-top: 20px;">
                    <div class="metric-card">
                        <div class="metric-label">목표주가</div>
                        <div class="metric-value" style="font-size: 1.5em;">${recommendation.target_price_range || 'N/A'}</div>
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
                <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                    <p><strong>손절 힌트:</strong> ${recommendation.stop_loss_hint || 'N/A'}</p>
                    <p style="margin-top: 10px;">${recommendation.recommendation_comment || '추천 코멘트 없음'}</p>
                </div>
            </div>
        </div>
        
        <!-- 시장 현황 -->
        <div class="section">
            <div class="section-title">💰 시장 현황</div>
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
        
        <!-- 종합 점수 -->
        <div class="section">
            <div class="section-title">⭐ 종합 평가 점수</div>
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
        
        <!-- 재무 실적 -->
        <div class="section">
            <div class="section-title">💼 재무 실적 (${financial.latest_period || 'N/A'})</div>
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
        
        <!-- 기술적 분석 -->
        <div class="section">
            <div class="section-title">📈 기술적 분석</div>
            <div class="metrics-grid four-columns">
                <div class="metric-card">
                    <div class="metric-label">추세</div>
                    <div class="metric-value" style="font-size: 1.2em;">
                        ${getTrendEmoji(technical.trend)} ${getTrendText(technical.trend)}
                    </div>
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
                    <div class="metric-value" style="font-size: 1.2em;">${getVolatilityText(technical.volatility_20d_level)}</div>
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
        
        <!-- 뉴스 & 모멘텀 -->
        <div class="section">
            <div class="section-title">📰 뉴스 & 모멘텀</div>
            <div class="summary-box" style="margin-bottom: 15px;">
                <p><strong>감성:</strong> ${getSentimentEmoji(news.sentiment)} ${getSentimentText(news.sentiment)}</p>
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
        
        <!-- 투자 시나리오 -->
        <div class="section">
            <div class="section-title">🎯 향후 12개월 시나리오</div>
            <div class="summary-box" style="background: #f0fdf4; border-left: 4px solid #22c55e; margin-bottom: 15px;">
                <h4 style="color: #166534; margin-bottom: 8px;">🚀 강세 시나리오</h4>
                <p>${scenarios.bull_case?.description || 'N/A'}</p>
                <p style="margin-top: 8px;"><strong>예상 수익률:</strong> ${scenarios.bull_case?.expected_return_range || 'N/A'}</p>
            </div>
            <div class="summary-box" style="background: #fffbeb; border-left: 4px solid #f59e0b; margin-bottom: 15px;">
                <h4 style="color: #92400e; margin-bottom: 8px;">📊 기본 시나리오</h4>
                <p>${scenarios.base_case?.description || 'N/A'}</p>
                <p style="margin-top: 8px;"><strong>예상 수익률:</strong> ${scenarios.base_case?.expected_return_range || 'N/A'}</p>
            </div>
            <div class="summary-box" style="background: #fef2f2; border-left: 4px solid #ef4444; margin-bottom: 15px;">
                <h4 style="color: #991b1b; margin-bottom: 8px;">⚠️ 약세 시나리오</h4>
                <p>${scenarios.bear_case?.description || 'N/A'}</p>
                <p style="margin-top: 8px;"><strong>예상 수익률:</strong> ${scenarios.bear_case?.expected_return_range || 'N/A'}</p>
            </div>
            <div class="summary-box">
                <p>${scenarios.scenario_comment || '시나리오 분석 정보 없음'}</p>
            </div>
        </div>
        
        <!-- 리스크 -->
        <div class="section">
            <div class="section-title">⚠️ 주요 리스크</div>
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
                <div class="summary-box" style="background: ${severityColor}; border-left: 4px solid ${borderColor}; margin-bottom: 10px;">
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
            <div class="section-title">💡 투자 논리</div>
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
        
        <!-- 디버그 정보 (개발용) -->
        <details style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;">
            <summary style="cursor: pointer; font-weight: 600; color: #667eea;">🔍 상세 데이터 확인 (클릭)</summary>
            <pre style="margin-top: 10px; padding: 10px; background: white; border-radius: 4px; overflow-x: auto; font-size: 0.85em;">${JSON.stringify(data, null, 2)}</pre>
        </details>
    `;
    
    document.getElementById('resultContent').innerHTML = html;
}

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
    const emoji = {
        'uptrend': '🟢',
        'downtrend': '🔴',
        'sideways': '🟡'
    };
    return emoji[trend] || '⚪';
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
    const emoji = {
        'positive': '😊',
        'neutral': '😐',
        'negative': '😟'
    };
    return emoji[sentiment] || '😐';
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

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    loadAvailableStocks();
    loadAvailableModels();
});
