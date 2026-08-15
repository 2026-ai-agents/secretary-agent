"""v1.0의 약속: 조회는 관련분만, 갱신은 낡은 것을 지운다, 지어낸 key는 무시."""

import uuid

import pytest

from agent import graph as graph_module
from agent.memory import delete_memory, list_memories, save_memory, search_memories
from tests.conftest import ScriptedLLM, fake_response

TEST_USER = 990004


@pytest.fixture(autouse=True)
def clean_test_namespace():
    yield
    for m in list_memories(graph_module.store, TEST_USER):
        delete_memory(graph_module.store, TEST_USER, m["key"])


def wire(monkeypatch, responses):
    llm = ScriptedLLM(responses)
    monkeypatch.setattr(graph_module, "completion", llm)
    return llm


def cfg():
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}


def state(message: str) -> dict:
    return {"messages": [{"role": "user", "content": message}],
            "user_id": TEST_USER, "user_name": "테스트"}


def test_advisor_injects_at_most_limit(monkeypatch):
    for i in range(8):
        save_memory(graph_module.store, TEST_USER, f"기억 {i}번이다")
    llm = wire(monkeypatch, [
        fake_response(content="네!"),
        fake_response(content='{"add": [], "remove": []}'),
    ])
    graph_module.graph.invoke(state("안녕하세요"), cfg())
    system = llm.calls[0]["messages"][0]["content"]
    injected = [line for line in system.splitlines() if line.startswith("- 기억")]
    assert len(injected) == 5              # 전부(8)가 아니라 관련 상위 5개만


def test_memorize_replaces_stale_fact(monkeypatch):
    old_key = save_memory(graph_module.store, TEST_USER, "다음 달 성수동으로 이사한다")
    wire(monkeypatch, [
        fake_response(content="이사 축하드려요!"),
        fake_response(content=f'{{"add": ["성수동에 산다"], "remove": ["{old_key}"]}}'),
    ])
    graph_module.graph.invoke(state("저 이사 끝났어요! 이제 성수동 주민이에요"), cfg())
    facts = [m["fact"] for m in list_memories(graph_module.store, TEST_USER)]
    assert facts == ["성수동에 산다"]      # 낡은 기억은 사라지고 새 사실만 남았다


def test_memorize_ignores_invented_keys(monkeypatch):
    key = save_memory(graph_module.store, TEST_USER, "견과류 알레르기가 있다")
    wire(monkeypatch, [
        fake_response(content="네!"),
        fake_response(content='{"add": [], "remove": ["no-such-key"]}'),
    ])
    graph_module.graph.invoke(state("안녕하세요"), cfg())
    assert [m["key"] for m in list_memories(graph_module.store, TEST_USER)] == [key]


def test_search_respects_namespace_and_limit():
    for i in range(4):
        save_memory(graph_module.store, TEST_USER, f"사실 {i}번이다")
    hits = search_memories(graph_module.store, TEST_USER, query="사실", limit=2)
    assert len(hits) == 2
    assert all(h["score"] is not None for h in hits)
