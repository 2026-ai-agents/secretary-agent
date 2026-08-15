"""v0.2 시연: 두 사실, 두 서랍 — 새 대화에서 누가 살아남는가.

thread A에서 사실 두 개를 말한다.
  · 하나는 "기억해 줘"라고 부탁한다 → remember 도구 → store (사용자 서랍)
  · 하나는 흘리듯 말만 한다        → checkpoint (thread 열쇠)에만 남는다

새 대화(thread B)에서 둘 다 물어보면, store에 넣은 것만 돌아온다.
같은 대화에 있던 두 사실의 운명이 저장된 곳 때문에 갈린다 — 단기와
장기의 경계를 이보다 좁게 자를 수는 없다.
"""

import httpx

APP = "http://localhost:8000"


def chat(thread_id: str, message: str) -> None:
    r = httpx.post(f"{APP}/chat", json={
        "user_id": 1, "user_name": "김서연",
        "thread_id": thread_id, "message": message,
    }, timeout=120)
    r.raise_for_status()
    print(f"[김서연] {message}")
    print(f"[단비] {r.json()['answer']}\n")


a = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
print(f"=== thread A ({a}) — 두 사실을 말한다 ===\n")
chat(a, "기억해 주세요. 저는 커피를 못 마셔서 회의 때 디카페인으로 부탁해요.")
chat(a, "아 그리고 요즘 테니스에 푹 빠져 있어요.")

b = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
print(f"=== thread B ({b}) — 새 대화에서 둘 다 물어본다 ===\n")
chat(b, "제가 회의 때 마실 것 뭐로 부탁했었죠?")
chat(b, "요즘 제가 뭐에 빠져 있다고 했죠?")

memories = httpx.get(f"{APP}/memories/1", timeout=10).json()["memories"]
print("=== store에 실제로 든 것 ===")
for m in memories:
    print(f"  💭 {m['fact']}")
