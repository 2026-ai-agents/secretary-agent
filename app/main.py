"""secretary-agent app — 뼈대: /health 하나."""

from fastapi import FastAPI

app = FastAPI(title="secretary-agent", version="0.0")


@app.get("/health")
def health():
    return {"ok": True, "version": app.version}
