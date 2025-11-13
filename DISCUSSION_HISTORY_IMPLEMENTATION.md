# 전문가 의견 표시 기능 구현 완료

## 📋 구현 내용

### 1. UI에 discussion_history 섹터 추가 (index.js)

**위치**: AI 종합 브리핑과 성과 지표 사이

**기능**:
- `data.discussion_history` 배열이 있는 경우에만 표시 (멀티에이전트 전용)
- 각 전문가의 의견을 색상으로 구분하여 카드 형식으로 표시

**전문가 타입 감지**:
```javascript
- 재무 전문가 (💰): 초록색 (#28a745)
- 기술 전문가 (📊): 파란색 (#007bff)
- 뉴스 전문가 (📰): 빨간색 (#dc3545)
```

**자동 태그 제거**:
- `[재무 전문가]`, `[기술 전문가]`, `[뉴스 전문가]` 등의 태그를 자동으로 제거
- 영문 태그도 지원 (Financial Agent, Technical Agent, News Agent)

### 2. PDF 내보내기에 스타일 추가 (index.js)

**추가된 CSS 클래스**:
```css
.expert-opinion-card
.expert-header
.expert-content
```

**특징**:
- PDF에서도 전문가 의견이 잘 보이도록 최적화된 스타일
- `page-break-inside: avoid`로 카드가 페이지 중간에서 잘리지 않도록 처리
- 폰트 크기 조정 (화면: 13px, PDF: 10px)

### 3. 백엔드 데이터 전달 (portfolio_endpoint.py)

**parse_agent_result 함수 수정**:
```python
return {
    "ai_summary": result.get("ai_summary"),
    "portfolio_allocation": result.get("portfolio_allocation"),
    "performance_metrics": result.get("performance_metrics"),
    "chart_data": result.get("chart_data"),
    "discussion_history": result.get("discussion_history", [])  # ⭐ 추가
}
```

## 🎯 동작 방식

### Anthropic 엔진 (단일 에이전트)
- `discussion_history` 없음
- 전문가 의견 섹션 표시 안 됨

### LangGraph 엔진 (멀티 에이전트)
- 3개 전문가 (재무/기술/뉴스)가 각각 분석 요약 생성
- `discussion_history` 배열에 순서대로 저장
- UI에서 색상과 아이콘으로 구분하여 표시
- PDF 내보내기 시에도 포함

## 📊 데이터 구조 예시

```json
{
  "ai_summary": "AI 종합 분석...",
  "discussion_history": [
    "[재무 전문가] 삼성전자는 견고한 재무구조를 보유하고 있으며...",
    "[기술 전문가] RSI 지표가 중립권에 위치하고 있으며...",
    "[뉴스 전문가] 최근 AI 반도체 수요 증가와 관련된 긍정적 뉴스가..."
  ],
  "portfolio_allocation": [...],
  "performance_metrics": {...}
}
```

## 🧪 테스트 방법

### 1. 로컬 테스트 파일
`experiments/test_discussion_display.html`에서 시각적 확인 가능

### 2. 실제 환경 테스트
1. FastAPI 서버 실행:
   ```powershell
   cd experiments
   python portfolio_endpoint.py
   ```

2. 브라우저에서 `http://localhost:8000` 접속

3. **LangGraph 엔진 선택** (중요!)

4. 섹터/종목 선택 후 분석 실행

5. 결과 화면에서 "👥 전문가 분석 의견" 섹션 확인

6. "📄 PDF 다운로드" 버튼으로 PDF에도 포함되는지 확인

## ✅ 완료된 작업

- [x] UI에 discussion_history 렌더링 로직 추가
- [x] 전문가 타입 자동 감지 및 색상/아이콘 매핑
- [x] PDF 내보내기 스타일 추가
- [x] 백엔드에서 discussion_history 전달
- [x] 테스트 HTML 페이지 생성

## 🎨 UI 스크린샷 설명

**전문가 분석 의견 섹션**:
```
┌─────────────────────────────────────────────┐
│ 👥 전문가 분석 의견                          │
├─────────────────────────────────────────────┤
│ ┌───────────────────────────────────────┐   │
│ │ 💰 재무 전문가              [초록색]   │   │
│ │ 삼성전자는 견고한 재무구조를...        │   │
│ └───────────────────────────────────────┘   │
│                                             │
│ ┌───────────────────────────────────────┐   │
│ │ 📊 기술 전문가              [파란색]   │   │
│ │ RSI 지표가 중립권에...                │   │
│ └───────────────────────────────────────┘   │
│                                             │
│ ┌───────────────────────────────────────┐   │
│ │ 📰 뉴스 전문가              [빨간색]   │   │
│ │ 최근 AI 반도체 수요...                │   │
│ └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## 📝 참고사항

- Anthropic 엔진에서는 전문가 의견 섹션이 표시되지 않음 (정상 동작)
- LangGraph 엔진만 멀티에이전트 시스템을 사용하므로 discussion_history 생성
- PDF 내보내기는 Playwright로 처리되며, JavaScript 차트도 정상 렌더링됨
