"""v0.2의 약속: 서랍은 사용자별이고, 기억은 프롬프트에 실리며, thread를 넘는다."""

import json
import uuid

import pytest

from agent import graph as graph_module
from agent import tools
from agent.memory import delete_memory, list_memories, ns, save_memory
from tests.conftest import ScriptedLLM, fake_response, fake_tool_call

TEST_USER = 990001
OTHER_USER = 990002


@pytest.fixture(autouse=True)
def clean_test_namespaces():
    yield
    for uid in (TEST_USER, OTHER_USER):
        for m in list_memories(graph_module.store, uid):
            delete_memory(graph_module.store, uid, m["key"])


def wire(monkeypatch, responses):
    llm = ScriptedLLM(responses)
    monkeypatch.setattr(graph_module, "completion", llm)
    return llm


def cfg():
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}


def state(message: str) -> dict:
    return {"messages": [{"role": "user", "content": message}],
            "user_id": TEST_USER, "user_name": "테스트"}


def test_namespaces_isolate_users():
    save_memory(graph_module.store, TEST_USER, "견과류 알레르기가 있다")
    assert [m["fact"] for m in list_memories(graph_module.store, TEST_USER)] \
        == ["견과류 알레르기가 있다"]
    assert list_memories(graph_module.store, OTHER_USER) == []


def test_remember_tool_writes_to_store():
    result = json.loads(tools.run_tool(
        "remember", '{"fact": "회의는 오전을 선호한다"}', user_id=TEST_USER))
    assert result["remembered"] == "회의는 오전을 선호한다"
    assert "회의는 오전을 선호한다" in [
        m["fact"] for m in list_memories(graph_module.store, TEST_USER)]


def test_memories_ride_the_system_prompt(monkeypatch):
    save_memory(graph_module.store, TEST_USER, "커피 대신 디카페인을 마신다")
    llm = wire(monkeypatch, [fake_response(content="디카페인으로 준비할게요!")])
    graph_module.graph.invoke(state("회의 준비해 줘"), cfg())
    system = llm.calls[0]["messages"][0]["content"]
    assert "커피 대신 디카페인을 마신다" in system     # 서랍이 프롬프트에 실렸다


def test_store_memory_crosses_threads(monkeypatch):
    """v0.1에서 백지였던 바로 그 시나리오 — 이제 store가 잇는다."""
    llm = wire(monkeypatch, [
        fake_response(tool_calls=[fake_tool_call(
            "remember", '{"fact": "견과류 알레르기가 있다"}')]),
        fake_response(content="기억해 둘게요!"),
        fake_response(content="견과류 알레르기가 있으시죠."),
    ])
    graph_module.graph.invoke(state("견과류 알레르기 기억해 줘"), cfg())
    graph_module.graph.invoke(state("제가 무슨 알레르기가 있다고 했죠?"), cfg())  # 새 thread
    system = llm.calls[2]["messages"][0]["content"]
    assert "견과류 알레르기가 있다" in system
