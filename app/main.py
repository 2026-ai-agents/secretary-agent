"""secretary-agent app — v0.1: 로그인(식별)과 비서 대화. 기억은 thread 안에만.

booking-agent의 규약을 그대로 잇는다: 이름+전화(숫자만 저장) 식별,
/history의 대화 복원. 다른 점 하나 — thread는 사용자마다 하나가 아니라
**대화마다 하나**다. "새 대화" 버튼이 새 thread를 여는 것이 이 저장소의
핵심 동작이고, v0.1에서는 그때마다 비서가 백지가 된다.
"""

import re
import uuid

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.graph import graph, store
from agent.memory import delete_memory, list_memories
from agent.tools import DATABASE_URL

app = FastAPI(title="secretary-agent", version="1.0")


@app.get("/health")
def health():
    return {"ok": True, "version": app.version}


def normalize_phone(raw: str) -> str:
    """숫자만 남긴다 — 010-1111-2222와 01011112222는 같은 사용자다."""
    return re.sub(r"\D", "", raw)


def new_thread_id(user_id: int) -> str:
    return f"u{user_id}-{uuid.uuid4().hex[:6]}"


class LoginBody(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=4)


@app.post("/login")
def login(body: LoginBody):
    """이름+전화로 사용자를 찾거나 만들고, 새 대화 thread를 하나 연다."""
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """INSERT INTO users (name, phone) VALUES (%s, %s)
               ON CONFLICT (phone) DO UPDATE SET name = EXCLUDED.name
               RETURNING id, name""",
            (body.name, normalize_phone(body.phone)),
        ).fetchone()
        conn.commit()
    user_id, name = row
    return {"user_id": user_id, "name": name, "thread_id": new_thread_id(user_id)}


@app.get("/user/{user_id}")
def user(user_id: int):
    """새로고침한 화면이 로그인을 복원할 때 쓴다 — URL에는 id만 실린다."""
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT id, name FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="없는 사용자다")
    return {"user_id": row[0], "name": row[1]}


@app.post("/threads/{user_id}")
def open_thread(user_id: int):
    """새 대화 — v0.1에서는 이 순간 비서가 백지가 된다."""
    return {"thread_id": new_thread_id(user_id)}


@app.get("/history/{thread_id}")
def history(thread_id: str):
    """새로고침한 화면이 이 thread의 대화를 checkpointer에서 복원한다."""
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    return {"messages": [
        {"role": m["role"], "content": m["content"]}
        for m in snapshot.values.get("messages", [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]}


@app.get("/events/{user_id}")
def events(user_id: int):
    """사이드바용 — 오늘 이후 일정. 도메인 행은 thread와 무관하게 남는다."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """SELECT id, title, event_date, event_time FROM events
               WHERE user_id = %s AND event_date >= CURRENT_DATE
               ORDER BY event_date, event_time NULLS LAST""",
            (user_id,),
        ).fetchall()
    return {"events": [
        {"event_id": r[0], "title": r[1], "date": str(r[2]),
         "time": str(r[3])[:5] if r[3] else None}
        for r in rows
    ]}


@app.get("/memories/{user_id}")
def memories(user_id: int):
    """사이드바용 — 단비가 이 사용자에 대해 기억하는 것 (장기 기억)."""
    return {"memories": list_memories(store, user_id)}


@app.delete("/memories/{user_id}/{key}")
def forget(user_id: int, key: str):
    """내 기억은 내가 지운다 — 사이드바의 🗑 버튼이 부른다."""
    delete_memory(store, user_id, key)
    return {"deleted": key}


class ChatBody(BaseModel):
    user_id: int
    user_name: str = "사용자"
    thread_id: str
    message: str


@app.post("/chat")
def chat(body: ChatBody):
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": body.message}],
            "user_id": body.user_id,
            "user_name": body.user_name,
        },
        {"configurable": {"thread_id": body.thread_id}},
    )
    return {"answer": result["messages"][-1]["content"]}
