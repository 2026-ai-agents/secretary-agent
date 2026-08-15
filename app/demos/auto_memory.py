"""v0.3 시연: 부탁하지 않아도 담을 것을 담고, 잡담은 버린다.

thread A에서 "기억해 줘" 없이 두 가지를 말한다.
  · 오래 갈 사실 (다음 달 성수동 이사)
  · 그때뿐인 잡담 (오늘 날씨가 덥다)

턴이 끝날 때마다 memorize 노드가 판단한다. store를 열어 무엇이 담기고
무엇이 버려졌는지 확인하고, 새 대화에서 이사 계획을 기억하는지 본다.
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


def show_memories(label: str) -> None:
    memories = httpx.get(f"{APP}/memories/1", timeout=10).json()["memories"]
    print(f"=== {label} ===")
    for m in memories:
        print(f"  💭 {m['fact']}")
    if not memories:
        print("  (없음)")
    print()


show_memories("시작 전 store")

a = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
print(f"=== thread A ({a}) — '기억해 줘' 없이 말한다 ===\n")
chat(a, "다음 달에 성수동으로 이사 가요. 이사 끝나면 집들이도 해야 하고 정신없네요.")
chat(a, "오늘 날씨 진짜 덥네요. 아이스크림 생각나는 날이에요.")

show_memories("두 턴 뒤의 store — 이사는 담기고 날씨는 버려졌나")

b = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
print(f"=== thread B ({b}) — 새 대화 ===\n")
chat(b, "저 어디로 이사 간다고 했었죠?")
