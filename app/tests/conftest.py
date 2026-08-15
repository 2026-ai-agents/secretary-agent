"""LLM을 부르지 않는 테스트 대역 — booking-agent와 같은 규약.

임베딩도 대역이다: 텍스트 해시로 만든 결정적 벡터라 키 없이 돌고,
put/search의 **기계 동작**(인덱싱·limit·격리)을 검증한다. 의미 순위의
품질은 실제 임베딩의 몫이라 데모에서 실측한다.
"""

import hashlib
import struct
from types import SimpleNamespace

import pytest

from agent import memory
from agent.config import EMBED_DIMS


def fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        raw = hashlib.sha256(text.encode()).digest()
        floats = [struct.unpack(">H", raw[i % 32:i % 32 + 2])[0] / 65535
                  for i in range(0, EMBED_DIMS * 2, 2)]
        vectors.append(floats)
    return vectors


@pytest.fixture(autouse=True)
def keyless_embedder(monkeypatch):
    monkeypatch.setattr(memory, "EMBEDDER", fake_embed)


def fake_tool_call(name: str, arguments: str, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
        type="function",
    )


def fake_response(content=None, tool_calls=None):
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        role="assistant",
        model_dump=lambda: {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in (tool_calls or [])
            ]
            or None,
        },
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], model="fake-model")


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("각본에 없는 추가 LLM 호출")
        return self.responses.pop(0)
