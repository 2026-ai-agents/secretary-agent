"""v1.0 시연: 사실은 변한다 — 낡은 기억을 지우고 갈아 끼운다.

v0.3 데모가 남긴 기억("다음 달에 성수동으로 이사한다")이 있는 상태에서
"이사 끝났어요"라고 말하면, memorize 판단기가 낡은 기억을 remove하고
새 사실("성수동에 산다")을 add한다. 서랍은 쌓이기만 하는 창고가 아니다.
"""

import httpx

APP = "http://localhost:8000"


def show_memories(label: str) -> None:
    memories = httpx.get(f"{APP}/memories/1", timeout=10).json()["memories"]
    print(f"=== {label} ===")
    for m in memories:
        print(f"  💭 {m['fact']}")
    print()


show_memories("말하기 전의 store")

thread = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
message = "저 이사 끝났어요! 이제 성수동 주민이에요. 새집에서 첫 출근이었어요."
r = httpx.post(f"{APP}/chat", json={
    "user_id": 1, "user_name": "김서연",
    "thread_id": thread, "message": message,
}, timeout=120)
r.raise_for_status()
print(f"[김서연] {message}")
print(f"[단비] {r.json()['answer']}\n")

show_memories("말한 뒤의 store — 이사 예정은 사라지고, 사는 곳이 갱신됐나")
