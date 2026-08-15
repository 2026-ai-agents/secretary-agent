"""비서 그래프 — v0.2: 장기 기억(store)이 연결된다.

thread별 열쇠(checkpointer)에 더해 **사용자별 서랍(store)**이 생긴다.
advisor는 매 턴 서랍을 열어 기억을 시스템 프롬프트에 싣고, 사용자가
기억을 부탁하면 remember 도구가 서랍에 넣는다. 서랍은 thread와 무관하게
사용자에게 붙어 있으므로, "새 대화"를 열어도 기억이 이어진다.

단, v0.2의 저장은 **명시적**이다 — "기억해 줘"라고 말해야 저장된다.
흘리듯 말한 사실을 스스로 담는 것은 v0.3(기억 판단)의 몫이다.
"""

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
from agent.memory import list_memories, render_memories
from agent.tools import DATABASE_URL, run_tool, tool_schemas

SYSTEM_PROMPT = """당신은 개인 비서 '단비'다. {user_name} 님의 일정을 챙기고 하루를 돕는다.

## 진행 방법
- 일정을 잡아 달라면 add_event로 잡고, 일정 질문에는 my_events로 확인해 답한다.
  일정을 지어내지 않는다.
- 사용자가 **명시적으로 "기억해 줘"라고 부탁할 때만** remember로 장기 기억에
  저장한다. 부탁받지 않은 이야기는 저장하지 않는다.
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


def route_after_advisor(state: SecretaryState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    return "tools" if last.get("tool_calls") else END


# ── 선언부 ────────────────────────────────────────────────────────────
builder = StateGraph(SecretaryState)
builder.add_node("advisor", advisor)
builder.add_node("tools", tools)
builder.add_edge(START, "advisor")
builder.add_conditional_edges("advisor", route_after_advisor, {"tools": "tools", END: END})
builder.add_edge("tools", "advisor")

# 두 기억이 같은 pg를 나눠 쓴다: thread별 열쇠(checkpointer)와
# 사용자별 서랍(store). setup()은 각자 자기 테이블을 만든다 (멱등).
pool = ConnectionPool(DATABASE_URL, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()
store = PostgresStore(pool)
store.setup()

graph = builder.compile(checkpointer=checkpointer, store=store)
