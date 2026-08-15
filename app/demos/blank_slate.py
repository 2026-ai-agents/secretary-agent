"""v0.1 사고 재현: 새 대화를 열면 비서가 나를 처음 본 사람이 된다.

서버의 /chat API로 진행한다 (기억의 주인은 서버다).

  1) thread A — 알레르기를 말하고 치과 일정을 잡는다
  2) thread A — 같은 대화에서는 알레르기를 기억한다
  3) thread B(새 대화) — 일정은 조회된다 (db 행이니까).
     그러나 알레르기는 백지다 (대화 기억은 thread 안에 갇혀 있으니까)

도메인 데이터와 대화 기억의 수명이 다르다는 것, 그 간극이 v0.2부터의
주제(장기 기억 store)다.
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
print(f"=== thread A ({a}) ===\n")
chat(a, "저 견과류 알레르기가 있어요. 그리고 다음 주 화요일 15시에 치과 예약 잡아 주세요.")
chat(a, "제가 무슨 알레르기가 있다고 했죠?")

b = httpx.post(f"{APP}/threads/1", timeout=10).json()["thread_id"]
print(f"=== thread B ({b}) — 새 대화 ===\n")
chat(b, "다음 주에 제 일정이 뭐가 있죠?")
chat(b, "제가 무슨 알레르기가 있다고 했죠?")
