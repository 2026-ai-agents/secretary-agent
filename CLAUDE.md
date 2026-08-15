# CLAUDE.md

AI Agent 실전 Day 2 ③: 단기 기억과 장기 기억의 구분을 배우는 개인 비서
웹 제품. 릴리즈 사다리 v0.1(단기만) → v0.2(store 연결) → v0.3(기억 판단)
→ v1.0(의미 검색·갱신)으로 자란다. 이 문서는 이 저장소에서 작업하는
AI 도구를 위한 가이드다.

## 실행·검증 (전부 컨테이너에서)

```sh
docker compose up --build          # app(8000) · ui(8501) · db 기동
docker compose exec app pytest     # 유닛 테스트 — LLM은 각본 대역, db는 진짜
docker compose exec app python demos/blank_slate.py   # 시연은 app/demos/
```

로컬 파이썬으로 돌리지 않는다. 테스트는 키 없이 통과해야 정상이다.
db는 pgvector 이미지 + named volume(pgdata)이다. 초기화는 down -v로만.

## Git 워크플로: git flow

- `develop`에서 `feature/*` 분기 → `develop` 머지. `main` 직접 커밋 금지
- 릴리즈 사다리: `release/<태그>` → `main` 머지 + annotated 태그 + GitHub
  Release + `develop` 역머지. **태그를 옮기거나 지우지 않는다**
- 수정이 이전 태그의 동작을 바꾸면 안 된다

## 코드 규칙

- 모델·임베딩 문자열은 `app/agent/config.py`에만
- `app/agent/graph.py`가 교재의 중심 — 수정 시 강의 사이트의
  day-02-session-04 문서와 동기화한다
- 도구는 pydantic 모델 + `run_tool` 관문. 신원(user_id)은 상태에서 주입
- 장기 기억은 `("memories", user_id)` 네임스페이스 — 사용자 격리를 깨지
  않는다
- thread는 대화마다 하나("새 대화" 버튼). 사용자마다 하나가 아니다
- 데모는 HTTP API 경유로 쓴다 — 기억의 주인이 서버임을 정직하게 보인다
- 새 기능에는 테스트를 함께. 쓰기 테스트는 2099년 날짜 + 정리 fixture
- `.env`는 절대 커밋하지 않는다

## 강의 사이트와의 동기화

이 저장소의 내용이 바뀌면 강의 사이트(`2026-ai-agents`)의
day-02-session-04 문서도 함께 고친다.
