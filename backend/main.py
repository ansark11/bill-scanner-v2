import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import gmail, scan, bills

app = FastAPI(title="Bill Wrangler API")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gmail.router, prefix="/gmail", tags=["gmail"])
app.include_router(scan.router, prefix="/scan", tags=["scan"])
app.include_router(bills.router, prefix="/bills", tags=["bills"])


@app.get("/health")
async def health():
    return {"status": "ok"}
