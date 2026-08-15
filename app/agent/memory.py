"""장기 기억의 의미론 — 네임스페이스, 저장/조회 헬퍼, 임베딩.

checkpointer가 thread별 열쇠라면, store는 **사용자별 서랍**이다.
네임스페이스 ("memories", user_id)가 서랍의 주소이고, 다른 사용자의
서랍은 열리지 않는다. store 인스턴스 자체는 graph.py가 만들어
그래프에 주입한다 — 여기는 그 위의 규약만 둔다.

v1.0: 기억이 쌓이면 전부를 매 턴 실을 수 없다. put 때 임베딩이 함께
저장되고(store의 시맨틱 인덱스), 조회는 지금 발화와 **의미가 가까운
것**만 골라 온다.
"""

import uuid

from langgraph.store.base import BaseStore
from litellm import embedding

from agent.config import EMBED_DIMS, EMBED_MODEL


def _litellm_embed(texts: list[str]) -> list[list[float]]:
    response = embedding(model=EMBED_MODEL, input=texts, dimensions=EMBED_DIMS)
    return [item["embedding"] for item in response.data]


# 테스트가 결정적 대역으로 갈아끼우는 이음새 — 런타임은 litellm을 쓴다
EMBEDDER = _litellm_embed


def embed(texts: list[str]) -> list[list[float]]:
    return EMBEDDER(texts)


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


def search_memories(store: BaseStore, user_id: int, query: str, limit: int = 5) -> list[dict]:
    """지금 발화와 의미가 가까운 기억만 골라 온다 — v1.0의 조회 방식."""
    items = store.search(ns(user_id), query=query, limit=limit)
    return [{"key": item.key, "fact": item.value["fact"],
             "score": round(item.score, 3) if item.score is not None else None}
            for item in items]


def render_memories(memories: list[dict]) -> str:
    """시스템 프롬프트에 실을 모양 — 기억이 없으면 빈 문자열."""
    if not memories:
        return ""
    lines = "\n".join(f"- {m['fact']}" for m in memories)
    return f"\n## 기억하고 있는 것 (장기 기억, 지금 대화와 관련된 것만)\n{lines}\n"
