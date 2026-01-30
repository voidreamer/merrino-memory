from fastapi import FastAPI
from mangum import Mangum

from app.routers import memory, health

app = FastAPI(
    title="Merrino Memory",
    description="🐑🧠 Vector search over conversation transcripts and notes",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(memory.router, prefix="/api")

handler = Mangum(app, lifespan="off")
