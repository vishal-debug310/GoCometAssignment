import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi.middleware.cors import CORSMiddleware

import redis
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.auctions import router as auctions_router
from app.api.routes.bids import router as bids_router
from app.api.routes.participants import router as participants_router
from app.api.routes.rfqs import router as rfq_router
from app.core.config import settings
from app.core.database import engine
from app.websocket.pubsub import listen_for_auction_events
from app.websocket.routes import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Redis Pub/Sub listener when FastAPI starts.
    listener_task = asyncio.create_task(
        listen_for_auction_events()
    )

    try:
        yield
    finally:
        # Stop the listener cleanly during application shutdown.
        listener_task.cancel()

        with suppress(asyncio.CancelledError):
            await listener_task


app = FastAPI(
    title=settings.APP_NAME,
    description="GoComet - British Auction RFQ Management System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(rfq_router, prefix="/api")
app.include_router(participants_router, prefix="/api")
app.include_router(bids_router, prefix="/api")
app.include_router(auctions_router, prefix="/api")
app.include_router(websocket_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to GoComet API",
        "application": settings.APP_NAME,
        "status": "running",
    }


@app.get("/health")
def health_check():
    database_status = "connected"
    redis_status = "connected"

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "disconnected"

    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
    )

    try:
        client.ping()
    except Exception:
        redis_status = "disconnected"
    finally:
        client.close()

    result = {
        "application": "GoComet",
        "database": database_status,
        "redis": redis_status,
    }

    if database_status != "connected" or redis_status != "connected":
        raise HTTPException(status_code=503, detail=result)

    return {
        **result,
        "status": "healthy",
    }
