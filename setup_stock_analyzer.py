"""
단일 종목 분석 시스템 설정 스크립트

이 스크립트는 데이터베이스를 설정하고 필요한 데이터를 로드합니다.
"""

import sys
import subprocess
from pathlib import Path

def run_command(description, command):
    """명령어 실행 및 결과 출력"""
    print(f"\n{'='*60}")
    print(f"📌 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print("⚠️ 경고:", result.stderr)
        print(f"✅ {description} 완료")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 실패")
        print(f"에러: {e.stderr}")
        return False

def check_db_connection():
    """DB 연결 확인"""
    print("\n" + "="*60)
    print("🔍 데이터베이스 연결 확인")
    print("="*60)
    
    try:
        from core.db import healthcheck
        if healthcheck():
            print("✅ 데이터베이스 연결 성공")
            return True
        else:
            print("❌ 데이터베이스 연결 실패")
            return False
    except Exception as e:
        print(f"❌ 데이터베이스 연결 오류: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("🚀 단일 종목 분석 시스템 설정 시작")
    print("="*60)
    
    # 1. DB 연결 확인
    if not check_db_connection():
        print("\n❌ DB 연결 실패. .env 파일을 확인하세요")
        sys.exit(1)
    
    # 2. 종목 데이터 시드
    success = run_command(
        "1/4 - 종목 마스터 데이터 생성",
        "python jobs/seed_companies.py"
    )
    if not success:
        print("\n⚠️ 계속 진행하시겠습니까? (y/n)")
        if input().lower() != 'y':
            sys.exit(1)
    
    # 3. 주가 데이터 로드
    print("\n⚠️ 주가 데이터 로드는 시간이 오래 걸립니다 (5-10분)")
    print("   계속하시겠습니까? (y/n)")
    if input().lower() == 'y':
        success = run_command(
            "2/4 - 주가 데이터 로드 (yfinance)",
            "python jobs/load_prices_daily.py"
        )
        if not success:
            print("\n⚠️ 주가 데이터 로드 실패. 계속 진행하시겠습니까? (y/n)")
            if input().lower() != 'y':
                sys.exit(1)
    
    # 4. 재무 데이터 로드
    print("\n⚠️ 재무 데이터 로드도 시간이 걸립니다 (3-5분)")
    print("   계속하시겠습니까? (y/n)")
    if input().lower() == 'y':
        success = run_command(
            "3/4 - 재무 데이터 로드",
            "python jobs/load_fundamentals.py"
        )
        if not success:
            print("\n⚠️ 재무 데이터 로드 실패. 계속 진행하시겠습니까? (y/n)")
            if input().lower() != 'y':
                sys.exit(1)
    
    # 5. 기술적 지표 계산
    success = run_command(
        "4/4 - 기술적 지표 계산",
        "python jobs/calc_signals_latest.py"
    )
    if not success:
        print("\n⚠️ 기술적 지표 계산 실패")
    
    # 6. 데이터 확인
    print("\n" + "="*60)
    print("📊 데이터 확인")
    print("="*60)
    
    try:
        from core.db import fetch_one
        
        companies_count = fetch_one("SELECT COUNT(*) FROM companies")[0]
        prices_count = fetch_one("SELECT COUNT(DISTINCT ticker) FROM prices_daily")[0]
        fundamentals_count = fetch_one("SELECT COUNT(DISTINCT ticker) FROM fundamentals")[0]
        signals_count = fetch_one("SELECT COUNT(*) FROM signals_latest")[0]
        
        print(f"\n✅ 데이터 로드 완료:")
        print(f"   - 종목 수: {companies_count}")
        print(f"   - 주가 데이터: {prices_count}개 종목")
        print(f"   - 재무 데이터: {fundamentals_count}개 종목")
        print(f"   - 기술적 지표: {signals_count}개 종목")
        
        if prices_count > 0 and signals_count > 0:
            print("\n✅ 시스템이 준비되었습니다!")
            print("\n다음 명령어로 테스트하세요:")
            print("  python test_stock_analyzer.py tools")
            print("  python test_stock_analyzer.py full")
            print("\n또는 웹 서버를 실행하세요:")
            print("  cd experiments")
            print("  uvicorn stock_endpoint:app --port 8001 --reload")
        else:
            print("\n⚠️ 일부 데이터가 누락되었습니다. 위 명령어를 다시 실행하세요.")
    
    except Exception as e:
        print(f"\n❌ 데이터 확인 실패: {e}")
    
    print("\n" + "="*60)
    print("✅ 설정 완료")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
