from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import init_db
from app.routers import actions, admin, register
from app.services.limiter import limiter

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Authelia Self-Service Registration", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(register.router)
app.include_router(admin.router)
app.include_router(actions.router)
