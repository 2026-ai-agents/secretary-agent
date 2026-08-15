"""v0.3의 약속: 판단해서 담고, 잡담은 버리고, 판단이 죽어도 답변은 산다."""

import uuid

import pytest

from agent import graph as graph_module
from agent.memory import delete_memory, list_memories, save_memory
from tests.conftest import ScriptedLLM, fake_response

TEST_USER = 990003


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


def test_memorize_saves_judged_facts(monkeypatch):
    wire(monkeypatch, [
        fake_response(content="이사 준비 도와드릴게요!"),                  # advisor
        fake_response(content='{"add": ["다음 달 성수동으로 이사한다"], "remove": []}'),  # memorize
    ])
    graph_module.graph.invoke(state("다음 달에 성수동으로 이사 가요"), cfg())
    assert [m["fact"] for m in list_memories(graph_module.store, TEST_USER)] \
        == ["다음 달 성수동으로 이사한다"]


def test_memorize_discards_small_talk(monkeypatch):
    wire(monkeypatch, [
        fake_response(content="정말 덥죠!"),
        fake_response(content='{"add": [], "remove": []}'),
    ])
    graph_module.graph.invoke(state("오늘 날씨 진짜 덥네요"), cfg())
    assert list_memories(graph_module.store, TEST_USER) == []


def test_memorize_sees_known_facts_for_dedup(monkeypatch):
    save_memory(graph_module.store, TEST_USER, "견과류 알레르기가 있다")
    llm = wire(monkeypatch, [
        fake_response(content="네, 알고 있어요!"),
        fake_response(content='{"add": [], "remove": []}'),
    ])
    graph_module.graph.invoke(state("저 견과류 알레르기 있는 거 아시죠?"), cfg())
    # 기억 판단 프롬프트에 '이미 기억하는 것'이 실려 갔다
    assert "견과류 알레르기가 있다" in llm.calls[1]["messages"][0]["content"]


def test_broken_judgment_never_kills_the_answer(monkeypatch):
    wire(monkeypatch, [
        fake_response(content="알겠습니다!"),
        fake_response(content="이건 JSON이 아니다"),    # 판단기가 망가진 턴
    ])
    result = graph_module.graph.invoke(state("안녕하세요"), cfg())
    assert result["messages"][-1]["content"] == "알겠습니다!"   # 답은 살아 있다
    assert list_memories(graph_module.store, TEST_USER) == []
