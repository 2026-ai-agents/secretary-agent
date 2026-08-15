-- 시드: 사용자 1명 + 일정 2건 (상대 날짜 — 언제 기동해도 다음 주가 차 있다)

INSERT INTO users (name, phone) VALUES
    ('김서연', '01011112222');

INSERT INTO events (user_id, title, event_date, event_time) VALUES
    (1, '팀 주간 회의', CURRENT_DATE + 3, '10:00'),
    (1, '부모님 저녁 식사', CURRENT_DATE + 5, '19:00');
