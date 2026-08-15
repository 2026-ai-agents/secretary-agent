"""장기 기억의 의미론 — 네임스페이스와 저장/조회 헬퍼.

checkpointer가 thread별 열쇠라면, store는 **사용자별 서랍**이다.
네임스페이스 ("memories", user_id)가 서랍의 주소이고, 다른 사용자의
서랍은 열리지 않는다. store 인스턴스 자체는 graph.py가 만들어
그래프에 주입한다 — 여기는 그 위의 규약만 둔다.
"""

import uuid

from langgraph.store.base import BaseStore


def ns(user_id: int) -> tuple[str, str]:
    """사용자별 서랍 주소. 격리는 네임스페이스가 책임진다."""
    return ("memories", str(user_id))


def save_memory(store: BaseStore, user_id: int, fact: str) -> str:
    key = uuid.uuid4().hex[:8]
    store.put(ns(user_id), key, {"fact": fact})
    return key


def list_memories(store: BaseStore, user_id: int) -> list[dict]:
    items = store.search(ns(user_id), limit=50)
    return [{"key": item.key, "fact": item.value["fact"],
             "saved_at": item.created_at.isoformat()[:16]}
            for item in items]


def delete_memory(store: BaseStore, user_id: int, key: str) -> None:
    store.delete(ns(user_id), key)


def render_memories(memories: list[dict]) -> str:
    """시스템 프롬프트에 실을 모양 — 기억이 없으면 빈 문자열."""
    if not memories:
        return ""
    lines = "\n".join(f"- {m['fact']}" for m in memories)
    return f"\n## 기억하고 있는 것 (장기 기억)\n{lines}\n"
