"""
간단한 종목 분석 테스트 스크립트

사용 전 필수:
1. DB에 데이터가 있어야 합니다
   python jobs/seed_companies.py
   python jobs/load_prices_daily.py
   python jobs/load_fundamentals.py
   python jobs/calc_signals_latest.py

2. .env 파일에 DB 정보와 API 키 설정 필요
"""

from agent_test.stock_agent_anthropic import (
    get_stock_prices,
    get_financial_metrics,
    get_technical_signals,
    get_news_sentiment
)

def test_individual_tools():
    """각 Tool을 개별적으로 테스트"""
    
    ticker = "005930.KS"  # 삼성전자
    company_name = "삼성전자"
    
    print("\n" + "="*60)
    print("🧪 개별 Tool 테스트")
    print("="*60)
    
    # 1. 주가 데이터
    print("\n1️⃣ 주가 데이터 조회...")
    try:
        price_data = get_stock_prices(ticker, days=180)
        if 'error' in price_data:
            print(f"   ❌ 에러: {price_data['error']}")
        else:
            print(f"   ✅ 성공: {len([k for k, v in price_data.items() if v is not None])}개 필드")
            print(f"   - 현재가: {price_data.get('current_price', 'N/A')}")
            print(f"   - 1개월 수익률: {price_data.get('return_1m', 'N/A')}")
            print(f"   - 변동성: {price_data.get('volatility_20d', 'N/A')}")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    # 2. 재무 지표
    print("\n2️⃣ 재무 지표 조회...")
    try:
        financial_data = get_financial_metrics(ticker, quarters=4)
        if 'error' in financial_data:
            print(f"   ❌ 에러: {financial_data['error']}")
        else:
            print(f"   ✅ 성공: {len([k for k, v in financial_data.items() if v is not None])}개 필드")
            if financial_data.get('latest_data'):
                latest = financial_data['latest_data']
                print(f"   - 기준일: {latest.get('date', 'N/A')}")
                print(f"   - 매출액: {latest.get('revenue', 'N/A')}")
                print(f"   - 영업이익: {latest.get('op_income', 'N/A')}")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    # 3. 기술적 지표
    print("\n3️⃣ 기술적 지표 조회...")
    try:
        technical_data = get_technical_signals(ticker)
        if 'error' in technical_data:
            print(f"   ❌ 에러: {technical_data['error']}")
        else:
            print(f"   ✅ 성공: {len([k for k, v in technical_data.items() if v is not None])}개 필드")
            print(f"   - RSI: {technical_data.get('rsi14', 'N/A')}")
            print(f"   - 추세: {technical_data.get('trend', 'N/A')}")
            print(f"   - 모멘텀: {technical_data.get('momentum_20d', 'N/A')}")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    # 4. 뉴스 감성
    print("\n4️⃣ 뉴스 감성 분석...")
    try:
        news_data = get_news_sentiment(ticker, company_name)
        if 'error' in news_data:
            print(f"   ❌ 에러: {news_data['error']}")
        else:
            print(f"   ✅ 성공: {len([k for k, v in news_data.items() if v is not None])}개 필드")
            print(f"   - 뉴스 개수: {len(news_data.get('articles', []))}")
            print(f"   - 감성: {news_data.get('sentiment', 'N/A')}")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    print("\n" + "="*60)
    print("✅ 개별 Tool 테스트 완료")
    print("="*60 + "\n")


def test_full_analysis():
    """전체 분석 프로세스 테스트"""
    from agent_test.stock_agent_anthropic import run_stock_analysis_agent
    
    print("\n" + "="*60)
    print("🚀 전체 분석 프로세스 테스트")
    print("="*60 + "\n")
    
    ticker = "005930.KS"
    
    try:
        result = run_stock_analysis_agent(
            ticker=ticker,
            profile="balanced",
            model_name="gpt-4o"
        )
        
        if isinstance(result, dict):
            print("\n✅ 분석 완료!")
            print(f"   - 섹션 수: {len(result.keys())}")
            print(f"   - 주요 섹션: {list(result.keys())[:5]}")
            
            # raw_response 확인 (JSON 파싱 실패 시)
            if 'raw_response' in result:
                print(f"\n⚠️ JSON 파싱 실패 - raw_response 내용:")
                print(result['raw_response'][:500])  # 처음 500자만 출력
                print("...")
                return
            
            # 기본 정보 확인
            if 'basic_info' in result:
                basic = result['basic_info']
                print(f"\n   📊 기본 정보:")
                print(f"      - 종목명: {basic.get('name_kr', 'N/A')}")
                print(f"      - 시장: {basic.get('market', 'N/A')}")
            
            # 추천 확인
            if 'recommendation' in result:
                rec = result['recommendation']
                print(f"\n   🎯 투자 추천:")
                print(f"      - 의견: {rec.get('rating', 'N/A')}")
                print(f"      - 목표가: {rec.get('target_price_range', 'N/A')}")
        else:
            print(f"\n⚠️ 예상치 못한 결과 타입: {type(result)}")
            
    except Exception as e:
        print(f"\n❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("✅ 전체 분석 테스트 완료")
    print("="*60 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "tools":
        test_individual_tools()
    elif len(sys.argv) > 1 and sys.argv[1] == "full":
        test_full_analysis()
    else:
        print("\n사용법:")
        print("  python test_stock_analyzer.py tools  # 개별 Tool 테스트")
        print("  python test_stock_analyzer.py full   # 전체 분석 테스트")
        print()
