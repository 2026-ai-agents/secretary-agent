"""secretary-agent ui — 개인 비서 '단비' 화면 (v0.1).

thread는 사용자마다 하나가 아니라 **대화마다 하나**다. "새 대화" 버튼이
이 저장소의 주인공이다: v0.1에서는 그때마다 비서가 백지가 된다. 로그인과
현재 대화는 URL(?uid, ?tid)에 실려 새로고침을 살아남는다.
"""

import os

import requests
import streamlit as st

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")

st.set_page_config(page_title="단비 — 개인 비서", page_icon="🗓️")


def app_version() -> str:
    try:
        return requests.get(f"{APP_URL}/health", timeout=5).json()["version"]
    except requests.RequestException:
        return "?"


def load_history() -> None:
    h = requests.get(f"{APP_URL}/history/{st.session_state.thread_id}", timeout=10)
    h.raise_for_status()
    st.session_state.history = [(m["role"], m["content"]) for m in h.json()["messages"]]


# ── 새로고침 복원: URL의 uid·tid로 세션을 되살린다 ────────────────────
if "user" not in st.session_state and st.query_params.get("uid"):
    try:
        u = requests.get(f"{APP_URL}/user/{st.query_params['uid']}", timeout=10)
        u.raise_for_status()
        st.session_state.user = u.json()
        st.session_state.thread_id = st.query_params.get("tid") or requests.post(
            f"{APP_URL}/threads/{st.session_state.user['user_id']}", timeout=10
        ).json()["thread_id"]
        load_history()
    except requests.RequestException:
        st.query_params.clear()

# ── 로그인: 이름+전화가 사용자 식별자다 ───────────────────────────────
if "user" not in st.session_state:
    st.title("🗓️ 개인 비서 단비")
    st.caption("일정을 챙기고, 당신을 기억하는 비서입니다. 이름과 전화번호로 시작하세요.")
    with st.form("login"):
        name = st.text_input("이름", placeholder="김서연")
        phone = st.text_input("전화번호", placeholder="010-1234-5678")
        ok = st.form_submit_button("비서 시작", use_container_width=True)
    if ok and name.strip() and phone.strip():
        r = requests.post(f"{APP_URL}/login", json={"name": name.strip(), "phone": phone.strip()}, timeout=10)
        r.raise_for_status()
        body = r.json()
        st.session_state.user = {"user_id": body["user_id"], "name": body["name"]}
        st.session_state.thread_id = body["thread_id"]
        st.session_state.history = []
        st.query_params.update({"uid": str(body["user_id"]), "tid": body["thread_id"]})
        st.rerun()
    st.stop()

user = st.session_state.user

with st.sidebar:
    st.title("🗓️ 단비")
    st.caption(f"secretary-agent v{app_version()} · LangGraph")
    st.write(f"**{user['name']}** 님 · `{st.session_state.thread_id}`")
    if st.button("🆕 새 대화", use_container_width=True):
        t = requests.post(f"{APP_URL}/threads/{user['user_id']}", timeout=10)
        t.raise_for_status()
        st.session_state.thread_id = t.json()["thread_id"]
        st.session_state.history = []
        st.query_params["tid"] = st.session_state.thread_id
        st.rerun()
    if st.button("로그아웃", use_container_width=True):
        for key in ("user", "thread_id", "history"):
            st.session_state.pop(key, None)
        st.query_params.clear()
        st.rerun()
    st.divider()
    st.markdown("**단비가 기억하는 것**")
    try:
        remembered = requests.get(f"{APP_URL}/memories/{user['user_id']}", timeout=10).json()
        if not remembered["memories"]:
            st.caption("아직 기억하는 것이 없습니다.")
        for m in remembered["memories"]:
            fact_col, del_col = st.columns([6, 1])
            fact_col.caption(f"💭 {m['fact']}")
            if del_col.button("🗑", key=f"forget-{m['key']}", help="이 기억 지우기"):
                requests.delete(f"{APP_URL}/memories/{user['user_id']}/{m['key']}", timeout=10)
                st.rerun()
    except requests.RequestException:
        st.caption("기억을 불러오지 못했습니다.")
    st.divider()
    st.markdown("**다가오는 일정**")
    try:
        upcoming = requests.get(f"{APP_URL}/events/{user['user_id']}", timeout=10).json()
        if not upcoming["events"]:
            st.caption("예정된 일정이 없습니다.")
        for e in upcoming["events"]:
            st.caption(f"{e['date']} {e['time'] or '종일'} · {e['title']}")
    except requests.RequestException:
        st.caption("일정을 불러오지 못했습니다.")
    st.divider()
    st.markdown(
        "대화로 일정을 잡고 확인합니다.\n\n"
        "- 새 대화를 열면 이전 대화 맥락은 이어지지 않습니다"
    )

# ── 지난 대화 다시 그리기 ────────────────────────────────────────────
for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

# ── 입력 → /chat 왕복 ────────────────────────────────────────────────
if prompt := st.chat_input("예: 다음 주 화요일 3시에 치과 예약 잡아줘"):
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("단비가 확인 중…"):
            r = requests.post(
                f"{APP_URL}/chat",
                json={
                    "user_id": user["user_id"],
                    "user_name": user["name"],
                    "thread_id": st.session_state.thread_id,
                    "message": prompt,
                },
                timeout=120,
            )
            r.raise_for_status()
            answer = r.json()["answer"]
        st.markdown(answer)
    st.session_state.history.append(("assistant", answer))
