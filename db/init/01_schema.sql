-- secretary-agent 스키마: 개인 비서 '단비'의 사용자와 일정
--
-- 일정(events)은 도메인 데이터다 — db 행이므로 thread와 무관하게 남는다.
-- 대화 기억(checkpoint)과 장기 기억(store)은 여기 없다: v0.1에서
-- PostgresSaver가, v0.2에서 PostgresStore가 각각 자기 테이블을 만든다.
-- 이 셋의 수명 차이가 이 저장소의 교재다.

CREATE TABLE users (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    phone      text NOT NULL UNIQUE,      -- 가벼운 로그인의 식별자 (숫자만 저장)
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE events (
    id         serial PRIMARY KEY,
    user_id    int  NOT NULL REFERENCES users(id),
    title      text NOT NULL,
    event_date date NOT NULL,
    event_time time,                      -- 종일 일정이면 NULL
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_user_date ON events (user_id, event_date);
