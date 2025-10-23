import os
from openai import OpenAI

# .env에서 API 키를 가져옴
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# (임시) 실제로는 Firecrawl/Tavily를 연동해야 함
def get_fake_news_headlines(sector_name: str):
    """
    (임시 함수) 실제로는 Firecrawl/Tavily API를 호출해야 합니다.
    지금은 하드코딩된 뉴스를 반환합니다.
    """
    headlines_db = {
        "반도체": [
            "NVIDIA, HBM4 개발 공식화... AI 칩 경쟁 가속",
            "미국 정부, 중국 반도체 규제 추가 발표... 국내 업계 영향 촉각"
        ],
        "바이오": [
            "FDA, 신규 당뇨병 치료제 승인... 주가 급등",
            "임상 3상 실패 소식에 A제약 주가 하락"
        ]
    }
    return headlines_db.get(sector_name, ["관련 뉴스를 찾을 수 없습니다."])


def analyze_sector_sentiment(sector_name: str):
    """
    Agent 5 (뉴스 분석가)의 MVP 기능
    섹터 키워드로 뉴스를 검색(임시)하고, LLM을 통해 감성 분석을 수행합니다.
    """
    print(f"[Agent 5] 뉴스 분석가: '{sector_name}' 섹터 뉴스 감성 분석 시작...")

    # 1. 뉴스 수집 (지금은 임시 함수 호출)
    headlines = get_fake_news_headlines(sector_name)
    headlines_str = "\n".join(headlines)

    # 2. LLM을 통한 감성 분석
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini", # 또는 gpt-4o, gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "You are a financial news analyst. Analyze the sentiment of the following headlines for the given sector. Respond with only one word: 'Positive', 'Negative', or 'Neutral'."},
                {"role": "user", "content": f"Sector: {sector_name}\n\nHeadlines:\n{headlines_str}"}
            ],
            temperature=0
        )
        
        sentiment = completion.choices[0].message.content.strip()
        print(f"[Agent 5] 분석 완료. 감성: {sentiment}")
        
        return {
            "analyzed_headlines": headlines,
            "sentiment_signal": sentiment
        }
    except Exception as e:
        return {"error": str(e)}

