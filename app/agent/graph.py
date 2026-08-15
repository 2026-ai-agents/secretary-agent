"""비서 그래프 — v0.1: 단기 기억만. 새 대화(thread)를 열면 백지다.

booking-agent에서 완성한 것(advisor ↔ tools 순환, pg checkpointer,
신원 주입)을 그대로 딛는다. checkpointer 덕에 기억은 재시작을 넘는다 —
그러나 **thread를 넘지는 못한다**. 같은 사용자가 "새 대화"를 열면
알레르기도 취향도 백지에서 다시 시작한다.

한 가지 대조를 심어 둔다: 일정은 db 행이라 새 thread에서도 도구로
조회된다. 백지가 되는 것은 도메인 데이터가 아니라 **대화에서 흘린
사실들**이다. 그 사실들을 thread 너머로 옮기는 것이 v0.2부터의 주제다.
"""

import operator
from datetime import date
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from litellm import completion
from psycopg_pool import ConnectionPool

from agent.config import pick_model
from agent.tools import DATABASE_URL, run_tool, tool_schemas

SYSTEM_PROMPT = """당신은 개인 비서 '단비'다. {user_name} 님의 일정을 챙기고 하루를 돕는다.

## 진행 방법
- 일정을 잡아 달라면 add_event로 잡고, 일정 질문에는 my_events로 확인해 답한다.
  일정을 지어내지 않는다.
- 사용자가 취향·사정을 이야기하면 자연스럽게 대화에 반영한다.
- 오늘은 {today}다. "내일", "다음 주 화요일" 같은 상대 날짜는 이 기준으로 계산한다.

답은 간결하게 한국어로. {user_name} 님을 자연스럽게 부른다."""


class SecretaryState(TypedDict):
    """messages에는 reducer가 붙고(델타 반환), 신원 두 칸은 매 호출 덮어쓴다."""

    messages: Annotated[list[dict], operator.add]
    user_id: int
    user_name: str


def advisor(state: SecretaryState) -> dict:
    system = SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        user_name=state.get("user_name", "사용자"),
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

# 단기 기억: thread별 상태가 pg에 산다. 재시작은 넘지만 thread는 못 넘는다.
pool = ConnectionPool(DATABASE_URL, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()

graph = builder.compile(checkpointer=checkpointer)
