"""비서 그래프 — v1.0: 관련 기억만 꺼내 쓰고, 낡은 기억은 갈아 끼운다.

두 가지가 완성된다.

  · **의미 기반 조회** — 기억이 쌓이면 전부를 매 턴 실을 수 없다. store에
    시맨틱 인덱스(임베딩)가 붙고, advisor는 지금 발화와 의미가 가까운
    기억만 골라 싣는다.
  · **기억의 갱신** — 사실은 변한다("이사 갈 거예요" → "이사했어요").
    memorize 노드가 add뿐 아니라 remove도 판단해, 낡은 기억을 지우고
    새 사실로 갈아 끼운다. 서랍은 쌓이기만 하는 창고가 아니다.
"""

import json

import operator
from datetime import date
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.store.postgres import PostgresStore
from litellm import completion
from psycopg_pool import ConnectionPool

from agent.config import EMBED_DIMS, pick_model
from agent.memory import (delete_memory, embed, list_memories, render_memories,
                          save_memory, search_memories)
from agent.tools import DATABASE_URL, run_tool, tool_schemas

SYSTEM_PROMPT = """당신은 개인 비서 '단비'다. {user_name} 님의 일정을 챙기고 하루를 돕는다.

## 진행 방법
- 일정을 잡아 달라면 add_event로 잡고, 일정 질문에는 my_events로 확인해 답한다.
  일정을 지어내지 않는다.
- 사용자가 "기억해 줘"라고 부탁하면 remember로 즉시 저장한다. 부탁이 없어도
  괜찮다 — 대화가 끝날 때 별도의 기억 판단 단계가 담을 것을 담는다.
- 아래 "기억하고 있는 것"은 지난 대화들에서 저장된 장기 기억이다. 답할 때
  자연스럽게 활용하되, 지어내지 않는다.
- 오늘은 {today}다. "내일", "다음 주 화요일" 같은 상대 날짜는 이 기준으로 계산한다.
{memories}
답은 간결하게 한국어로. {user_name} 님을 자연스럽게 부른다."""


class SecretaryState(TypedDict):
    """messages에는 reducer가 붙고(델타 반환), 신원 두 칸은 매 호출 덮어쓴다."""

    messages: Annotated[list[dict], operator.add]
    user_id: int
    user_name: str


def advisor(state: SecretaryState, config, *, store: BaseStore) -> dict:
    """서랍을 여는 지점 — v1.0부터는 전부가 아니라 **관련 기억만** 싣는다."""
    last_user = next((m["content"] for m in reversed(state["messages"])
                      if m.get("role") == "user" and m.get("content")), "")
    memories = search_memories(store, state["user_id"], query=last_user, limit=5)
    system = SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        user_name=state.get("user_name", "사용자"),
        memories=render_memories(memories),
    )
    response = completion(
        model=pick_model(),
        messages=[{"role": "system", "content": system}, *state["messages"]],
        tools=tool_schemas(),
    )
    return {"messages": [response.choices[0].message.model_dump()]}


def tools(state: SecretaryState) -> dict:
    """요청된 도구를 전부 실행한다. user_id는 상태에서 주입 — LLM 인자가 아니다."""
    last = state["messages"][-1]
    return {
        "messages": [
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": run_tool(
                    call["function"]["name"],
                    call["function"]["arguments"],
                    user_id=state["user_id"],
                ),
            }
            for call in last["tool_calls"]
        ]
    }


MEMORIZE_PROMPT = """당신은 개인 비서의 기억 판단기다. 아래는 사용자와 비서의 이번 턴 대화다.

## 판단 기준
- 사용자에 대해 **오래 기억할 가치가 있는 사실**만 고른다: 취향, 건강·알레르기,
  가족·거처, 반복되는 습관, 앞으로의 대화에 계속 쓰일 사정.
- 잡담, 일회성 요청, 그때뿐인 감상은 버린다.
- "이미 기억하는 것"과 같은 내용은 다시 넣지 않는다.
- **사실이 변했으면 갈아 끼운다**: 낡은 기억의 key를 remove에 넣고, 새 사실을
  add에 넣는다 (예: "성수동으로 이사한다" → 이사가 끝났다면 remove + "성수동에 산다" add).
- 사실은 3인칭 한 문장으로 짧게 쓴다.

## 이미 기억하는 것 (key: 사실)
{known}

## 이번 턴 대화
{turn}

JSON 하나로만 답하라: {{"add": ["...", ...], "remove": ["key", ...]}} — 없으면 빈 배열"""


def memorize(state: SecretaryState, config, *, store: BaseStore) -> dict:
    """턴이 끝난 뒤의 기억 판단 — 판단 기준은 코드가 아니라 프롬프트에 산다.

    실패에 관대하다: JSON이 안 나오면 이번 턴은 그냥 기억하지 않는다.
    기억은 놓쳐도 다음 턴이 있지만, 답변이 죽으면 제품이 죽는다.
    """
    turn = []
    for message in reversed(state["messages"]):
        content = message.get("content")
        if content and message.get("role") in ("user", "assistant"):
            turn.append(f"[{message['role']}] {content}")
        if message.get("role") == "user":
            break
    known = list_memories(store, state["user_id"])
    response = completion(
        model=pick_model(),
        messages=[{"role": "user", "content": MEMORIZE_PROMPT.format(
            known="\n".join(f"- {m['key']}: {m['fact']}" for m in known) or "- (없음)",
            turn="\n".join(reversed(turn)),
        )}],
        response_format={"type": "json_object"},
    )
    try:
        verdict = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        verdict = {}
    known_keys = {m["key"] for m in known}
    for key in verdict.get("remove", []):
        if key in known_keys:                    # 판단기가 지어낸 key는 무시
            delete_memory(store, state["user_id"], key)
    for fact in verdict.get("add", []):
        if isinstance(fact, str) and fact.strip():
            save_memory(store, state["user_id"], fact.strip())
    return {}


def route_after_advisor(state: SecretaryState) -> Literal["tools", "memorize"]:
    """답이 나왔으면 끝이 아니라 기억 판단으로 — END 앞에 한 정거장이 생겼다."""
    last = state["messages"][-1]
    return "tools" if last.get("tool_calls") else "memorize"


# ── 선언부 ────────────────────────────────────────────────────────────
builder = StateGraph(SecretaryState)
builder.add_node("advisor", advisor)
builder.add_node("tools", tools)
builder.add_node("memorize", memorize)
builder.add_edge(START, "advisor")
builder.add_conditional_edges("advisor", route_after_advisor,
                              {"tools": "tools", "memorize": "memorize"})
builder.add_edge("tools", "advisor")
builder.add_edge("memorize", END)

# 두 기억이 같은 pg를 나눠 쓴다: thread별 열쇠(checkpointer)와
# 사용자별 서랍(store). setup()은 각자 자기 테이블을 만든다 (멱등).
# v1.0: store에 시맨틱 인덱스가 붙는다 — put 때 임베딩이 함께 저장되고,
# search(query=…)가 pgvector 위에서 의미 검색이 된다.
pool = ConnectionPool(DATABASE_URL, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()
store = PostgresStore(pool, index={"dims": EMBED_DIMS, "embed": embed})
store.setup()

graph = builder.compile(checkpointer=checkpointer, store=store)
