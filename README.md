# secretary-agent — 개인 비서 웹앱

AI Agent 실전 과정 Day 2 ③. 일정을 챙기면서, 대화 중 알게 된 취향·사실을
**장기 기억에 저장해 새 대화에서도 기억하는** 개인 비서 '단비'입니다.
**단기 기억(checkpointer, thread 안)과 장기 기억(store, thread를 넘어)의
구분**이 이 저장소의 주제입니다.

- 강의 사이트: [2026-ai-agents.github.io/2026-ai-agents](https://2026-ai-agents.github.io/2026-ai-agents/)
- 컨테이너 3개: `app`(FastAPI + LangGraph) · `ui`(Streamlit) · `db`(PostgreSQL + pgvector)

## 시작하기

```bash
git clone https://github.com/2026-ai-agents/secretary-agent.git
cd secretary-agent
cp .env.sample .env        # 키 채우기 (권장: Google — 의미 검색 임베딩에 필요)
docker compose up --build
```

- ui → http://localhost:8501 (비서 화면 — 이름+전화로 로그인)
- app → http://localhost:8000/docs (API)
- 테스트: `docker compose exec app pytest` (LLM 키 불필요, db는 진짜)

## 릴리즈 사다리

세션 진행과 1:1로 대응합니다. `git checkout <태그>` 후 `docker compose up
--build` 하면 그 시점의 동작이 재현됩니다.

| 릴리즈 | 상태 |
| --- | --- |
| v0.1 | 단기 기억만 — 새 대화(thread)를 열면 비서가 백지 |
| v0.2 | PostgresStore 연결: remember 도구로 저장, 매 턴 프롬프트에 주입 |
| v0.3 | 기억 판단: 턴이 끝날 때 memorize 노드가 담을 것을 스스로 고른다 |
| v1.0 | (예정) 의미 기반 검색 + 기억 갱신·삭제 완성 |

## 저장소 구조

```plaintext
secretary-agent/
├── docker-compose.yml      # app · ui · db (pgvector, named volume)
├── db/init/                # 확장(vector) + 스키마 + 시드
├── app/
│   ├── main.py             # FastAPI: /login /chat /threads /history /events
│   ├── agent/config.py     # 모델·임베딩 문자열이 사는 유일한 곳
│   ├── agent/graph.py      # ★ 교재의 중심 — 비서 그래프
│   ├── agent/tools.py      # add_event · my_events (신원은 주입)
│   ├── demos/              # 시연 스크립트
│   └── tests/              # 유닛 테스트 (LLM은 각본 대역)
└── ui/app.py               # 비서 화면 (Streamlit) — "새 대화" 버튼이 주인공
```

## 시연 스크립트

```bash
docker compose exec app python demos/blank_slate.py    # v0.1: 새 대화 = 백지 (일정은 남는데)
docker compose exec app python demos/two_memories.py   # v0.2: 두 사실, 두 서랍 — 누가 살아남나
docker compose exec app python demos/dump_store.py     # v0.2: 장기 기억의 실체도 pg의 행
docker compose exec app python demos/auto_memory.py    # v0.3: 부탁 없이 담고, 잡담은 버린다
```

## 세 가지 기억의 수명

| 저장소 | 무엇이 사는가 | 수명 |
| --- | --- | --- |
| `events` 테이블 | 일정 (도메인 데이터) | 영구 — thread와 무관 |
| checkpointer | 대화 상태 (단기 기억) | thread 안 — 새 대화면 백지 |
| store (v0.2\~) | 사용자에 대한 사실 (장기 기억) | thread를 넘어 사용자에 붙는다 |

## git 워크플로

git flow를 따릅니다: `develop`에서 `feature/*` 분기, 릴리즈는
`release/<태그>`를 거쳐 `main` 머지 + 태그. `main`은 항상 완성본입니다.
