-- PostgresStore의 시맨틱 인덱스(v1.0)가 벡터 컬럼을 쓸 수 있도록.
-- pgvector/pgvector 이미지에 확장이 들어 있고, 여기서 켠다.
CREATE EXTENSION IF NOT EXISTS vector;
