"""비서의 일정 도구 — booking-agent와 같은 규약.

pydantic 모델이 스키마와 검증을 겸하고, 실행은 run_tool 관문 하나로만
지나가며, 에러도 결과로 돌려준다. 신원(user_id)은 LLM 인자가 아니라
그래프 상태에서 주입한다.

일정은 db 행이라 thread와 무관하게 남는다 — v0.1에서 "새 대화를 열어도
일정은 조회되는데 대화에서 흘린 사실은 백지"라는 대조의 한 축이다.
"""

import json
import os
from datetime import date, time

import psycopg
from pydantic import BaseModel, Field, ValidationError

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://secretary:secretary@localhost:5432/secretarydb")


class AddEventArgs(BaseModel):
    """새 일정을 잡는다. 날짜는 필수, 시간은 없으면 종일 일정."""

    title: str = Field(min_length=1, description="일정 제목 (예: 치과 예약)")
    event_date: date = Field(description="날짜 (YYYY-MM-DD)")
    event_time: time | None = Field(default=None, description="시간 (HH:MM, 없으면 종일)")


def add_event(args: AddEventArgs, user_id: int) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """INSERT INTO events (user_id, title, event_date, event_time)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (user_id, args.title, args.event_date, args.event_time),
        ).fetchone()
        conn.commit()
    return {
        "event_id": row[0],
        "summary": f"{args.event_date}"
                   + (f" {str(args.event_time)[:5]}" if args.event_time else " 종일")
                   + f" · {args.title}",
    }


class MyEventsArgs(BaseModel):
    """이 사용자의 일정 목록을 조회한다 (오늘 이후)."""

    include_past: bool = Field(default=False, description="지난 일정도 포함할지")


def my_events(args: MyEventsArgs, user_id: int) -> dict:
    where = "" if args.include_past else "AND event_date >= CURRENT_DATE"
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            f"""SELECT id, title, event_date, event_time FROM events
                WHERE user_id = %s {where}
                ORDER BY event_date, event_time NULLS LAST""",
            (user_id,),
        ).fetchall()
    return {"events": [
        {"event_id": r[0], "title": r[1], "date": str(r[2]),
         "time": str(r[3])[:5] if r[3] else None}
        for r in rows
    ]}


class RememberArgs(BaseModel):
    """오래 기억할 가치가 있는 사실을 장기 기억에 저장한다. 새 대화에서도 유지된다."""

    fact: str = Field(min_length=1, description="기억할 사실 한 문장 (예: 견과류 알레르기가 있다)")


def remember(args: RememberArgs, user_id: int) -> dict:
    from agent.graph import store          # 실행 시점 임포트 — 순환을 피한다
    from agent.memory import save_memory

    key = save_memory(store, user_id, args.fact)
    return {"remembered": args.fact, "key": key,
            "notice": "장기 기억에 저장했다. 새 대화에서도 기억한다고 안내하라."}


REGISTRY: dict[str, tuple[type[BaseModel], object]] = {
    "add_event": (AddEventArgs, add_event),
    "my_events": (MyEventsArgs, my_events),
    "remember": (RememberArgs, remember),
}


def tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": (model.__doc__ or "").strip(),
                "parameters": model.model_json_schema(),
            },
        }
        for name, (model, _fn) in REGISTRY.items()
    ]


def run_tool(name: str, raw_arguments: str, user_id: int) -> str:
    entry = REGISTRY.get(name)
    if entry is None:
        return json.dumps({"error": f"없는 도구: {name}"}, ensure_ascii=False)
    args_model, fn = entry
    try:
        args = args_model.model_validate(json.loads(raw_arguments or "{}"))
    except (ValidationError, json.JSONDecodeError) as e:
        return json.dumps({"error": f"인자 검증 실패: {e}"}, ensure_ascii=False)
    return json.dumps(fn(args, user_id), ensure_ascii=False, default=str)
