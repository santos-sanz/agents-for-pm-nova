from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from hyper_demo.services.workshop_readiness import (
    WORKSHOP_ROOT,
    WorkshopReadiness,
    workshop_readiness,
)

app = FastAPI(title="Nova Workshop Readiness", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workshop/readiness", response_model=WorkshopReadiness)
def api_workshop_readiness() -> WorkshopReadiness:
    return workshop_readiness()


@app.get("/", response_class=HTMLResponse)
@app.get("/workshop", response_class=HTMLResponse)
@app.get("/workshop/", response_class=HTMLResponse)
def workshop_page() -> HTMLResponse:
    page = WORKSHOP_ROOT / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Workshop readiness page is missing.")
    return HTMLResponse(page.read_text(encoding="utf-8"))
