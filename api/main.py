"""
FastAPI entrypoint. Run locally with:
    uvicorn api.main:app --reload --port 8080
Then open http://127.0.0.1:8080 for the frontend, or http://127.0.0.1:8080/docs
for the interactive API explorer.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes import router
from tools.feedback_store import ensure_feedback_table_exists
from tools.alias_store import ensure_alias_table_exists
from tools.product_request_store import ensure_requests_table_exists

app = FastAPI(title="Data Mosaic API")

# Create the feedback logging, alias, and requests tables on startup if they don't exist yet
@app.on_event("startup")
def startup():
    try:
        ensure_feedback_table_exists()
    except Exception as e:
        print(f"Warning: could not ensure feedback table exists: {e}")
    try:
        ensure_alias_table_exists()
    except Exception as e:
        print(f"Warning: could not ensure alias table exists: {e}")
    try:
        ensure_requests_table_exists()
    except Exception as e:
        print(f"Warning: could not ensure requests table exists: {e}")


app.include_router(router, prefix="/api")

# Serve the simple frontend at the root URL
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
