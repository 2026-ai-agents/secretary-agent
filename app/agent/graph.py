"""비서 그래프 — v0.3: 무엇을 기억할지 스스로 판단한다.

v0.2의 기억은 "기억해 줘"라는 부탁이 있어야 저장됐다. 진짜 비서는
부탁받지 않아도 담을 것을 담는다. 매 턴이 끝날 때(답이 나온 뒤)
**memorize 노드**가 이번 턴의 대화를 읽고 "오래 기억할 가치가 있는
사실"을 골라 서랍에 넣는다 — 잡담은 버리고, 이미 아는 것은 다시 넣지
않는다. 판단 기준이 코드가 아니라 프롬프트에 산다는 것이 이 노드의
특징이자, 수업에서 들여다볼 지점이다.
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

from agent.config import pick_model
from agent.memory import list_memories, render_memories, save_memory
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
    """store는 compile(store=…)로 주입된다 — 서랍을 열어 프롬프트에 싣는 지점."""
    memories = list_memories(store, state["user_id"])
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
- 사실은 3인칭 한 문장으로 짧게 쓴다.

## 이미 기억하는 것
{known}

## 이번 턴 대화
{turn}

JSON 하나로만 답하라: {{"facts": ["...", ...]}} — 없으면 {{"facts": []}}"""


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
    known = [m["fact"] for m in list_memories(store, state["user_id"])]
    response = completion(
        model=pick_model(),
        messages=[{"role": "user", "content": MEMORIZE_PROMPT.format(
            known="\n".join(f"- {fact}" for fact in known) or "- (없음)",
            turn="\n".join(reversed(turn)),
        )}],
        response_format={"type": "json_object"},
    )
    try:
        facts = json.loads(response.choices[0].message.content or "{}").get("facts", [])
    except json.JSONDecodeError:
        facts = []
    for fact in facts:
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
pool = ConnectionPool(DATABASE_URL, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()
store = PostgresStore(pool)
store.setup()

graph = builder.compile(checkpointer=checkpointer, store=store)
