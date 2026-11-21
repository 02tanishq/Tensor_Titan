from contextlib import asynccontextmanager
from fastapi import FastAPI
from agentic.router import router as agentic_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Tensor Titan - Ujjwal Rail Agentic Action Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(agentic_router)


@app.get("/")
def root():
    return {"status": "online", "docs_url": "/docs"}
