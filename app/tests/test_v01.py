"""v0.1의 약속: 일정 도구는 신원을 지키고, 기억은 thread 안에 갇힌다."""

import json
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from agent import graph as graph_module
from agent import tools
from agent.tools import DATABASE_URL
from main import app
from tests.conftest import ScriptedLLM, fake_response, fake_tool_call

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_far_future():
    yield
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM events WHERE event_date >= '2099-01-01'")
        conn.commit()


def wire(monkeypatch, responses):
    llm = ScriptedLLM(responses)
    monkeypatch.setattr(graph_module, "completion", llm)
    return llm


def cfg():
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}


def state(message: str) -> dict:
    return {
        "messages": [{"role": "user", "content": message}],
        "user_id": 1,
        "user_name": "김서연",
    }


# ── 로그인·식별 ──────────────────────────────────────────────────────

def test_phone_formats_are_same_user():
    first = client.post("/login", json={"name": "테스트", "phone": "010-9999-0001"}).json()
    second = client.post("/login", json={"name": "테스트", "phone": "01099990001"}).json()
    assert first["user_id"] == second["user_id"]
    # 로그인마다 새 thread — 대화는 thread 단위다
    assert first["thread_id"] != second["thread_id"]


# ── 일정 도구 ────────────────────────────────────────────────────────

def test_add_event_writes_owned_row():
    result = json.loads(tools.run_tool(
        "add_event",
        '{"title": "치과 예약", "event_date": "2099-12-30", "event_time": "15:00"}',
        user_id=1,
    ))
    with psycopg.connect(DATABASE_URL) as conn:
        owner = conn.execute(
            "SELECT user_id FROM events WHERE id = %s", (result["event_id"],)
        ).fetchone()[0]
    assert owner == 1                      # 신원은 주입값 — LLM 인자가 아니다


def test_my_events_lists_only_own_rows():
    json.loads(tools.run_tool(
        "add_event", '{"title": "비밀 일정", "event_date": "2099-12-29"}', user_id=1))
    other = json.loads(tools.run_tool("my_events", "{}", user_id=2))
    assert "비밀 일정" not in [e["title"] for e in other["events"]]


# ── 단기 기억의 경계 ─────────────────────────────────────────────────

def test_same_thread_remembers(monkeypatch):
    llm = wire(monkeypatch, [
        fake_response(content="견과류 알레르기 기억할게요!"),
        fake_response(content="견과류 알레르기가 있으시죠."),
    ])
    config = cfg()
    graph_module.graph.invoke(state("저 견과류 알레르기 있어요"), config)
    graph_module.graph.invoke(state("제가 무슨 알레르기라고 했죠?"), config)
    sent = llm.calls[1]["messages"]
    assert [m.get("role") for m in sent] == ["system", "user", "assistant", "user"]


def test_new_thread_is_blank(monkeypatch):
    llm = wire(monkeypatch, [
        fake_response(content="기억할게요!"),
        fake_response(content="아직 말씀해 주신 적이 없어요."),
    ])
    graph_module.graph.invoke(state("저 견과류 알레르기 있어요"), cfg())
    graph_module.graph.invoke(state("제가 무슨 알레르기라고 했죠?"), cfg())   # 다른 thread
    # v0.1의 결핍: 새 thread의 첫 호출에는 이전 대화가 실려 가지 않는다
    assert [m.get("role") for m in llm.calls[1]["messages"]] == ["system", "user"]


def test_tool_roundtrip_hits_real_db(monkeypatch):
    wire(monkeypatch, [
        fake_response(tool_calls=[fake_tool_call(
            "add_event", '{"title": "치과", "event_date": "2099-12-28", "event_time": "15:00"}')]),
        fake_response(content="다음 주 치과 일정 잡아 뒀어요."),
    ])
    result = graph_module.graph.invoke(state("치과 예약 잡아줘"), cfg())
    tool_msg = [m for m in result["messages"] if m.get("role") == "tool"][0]
    assert "event_id" in json.loads(tool_msg["content"])
