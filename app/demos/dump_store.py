"""v0.2 시연: 서랍을 열어 본다 — 장기 기억의 실체도 pg의 행이다.

  1) SQL — store 테이블에 네임스페이스별로 행이 쌓여 있다
  2) store.search() — 같은 데이터를 store의 눈으로 읽은 모습

checkpoint 테이블과 나란히 있는 것도 봐 두자. 단기와 장기가 같은 db의
다른 테이블일 뿐이라는 것, 그것이 "거처가 다르다"의 실체다.
"""

import warnings

warnings.filterwarnings("ignore")   # upstream pending-deprecation 소음 차단 (수업 출력용)

import psycopg

from agent.graph import pool, store
from agent.memory import list_memories
from agent.tools import DATABASE_URL

print("=== 1) SQL: store 테이블에 뭐가 쌓였나 ===\n")
with psycopg.connect(DATABASE_URL) as conn:
    tables = [r[0] for r in conn.execute(
        """SELECT tablename FROM pg_tables WHERE schemaname='public'
           AND (tablename LIKE 'store%' OR tablename LIKE 'checkpoint%') ORDER BY 1"""
    ).fetchall()]
    print("기억 테이블:", ", ".join(tables))
    rows = conn.execute(
        "SELECT prefix, key, value FROM store ORDER BY prefix, created_at LIMIT 10"
    ).fetchall()
    for prefix, key, value in rows:
        print(f"  [{prefix}] {key}: {value}")

print("\n=== 2) store.search(): store의 눈으로 읽은 같은 데이터 ===\n")
for m in list_memories(store, 1):
    print(f"  💭 {m['fact']}  (저장: {m['saved_at']})")

pool.close()
