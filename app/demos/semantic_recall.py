"""v1.0 시연: 기억이 쌓여도, 지금 대화와 관련된 것만 실린다.

기억 여러 건을 채워 두고 서로 다른 질의로 검색해 보면, 질의마다 다른
기억이 위로 올라온다. 실제 임베딩(gemini-embedding-001)의 의미 순위를
실측하는 데모다 — advisor가 매 턴 하는 일이 정확히 이것이다.
"""

import warnings

warnings.filterwarnings("ignore")   # upstream pending-deprecation 소음 차단 (수업 출력용)

from agent.graph import pool, store
from agent.memory import list_memories, save_memory, search_memories

USER = 77   # 데모 전용 사용자 — 실행할 때마다 새로 채운다

for m in list_memories(store, USER):
    store.delete(("memories", str(USER)), m["key"])

FACTS = [
    "견과류 알레르기가 있다",
    "커피를 못 마셔서 회의 때 디카페인을 마신다",
    "회의는 오전을 선호한다",
    "고양이 두 마리를 키운다",
    "성수동에 산다",
    "매주 목요일 저녁에 테니스를 친다",
]
for fact in FACTS:
    save_memory(store, USER, fact)
print(f"기억 {len(FACTS)}건을 채웠다.\n")

for query in ["다음 회의 일정을 잡아 줘", "간식으로 쿠키 사 갈까 하는데", "주말에 뭐 하지"]:
    print(f"[질의] {query}")
    for h in search_memories(store, USER, query=query, limit=3):
        print(f"   score={h['score']:.3f}  {h['fact']}")
    print()

pool.close()
