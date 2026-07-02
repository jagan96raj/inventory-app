import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.auth import validate_auth_email_policy
from app.core.cors import parse_cors_origins
from app.core.health import check_database
from app.database import SessionLocal, engine
from app.routers import api_router
from app.services.idempotency import cleanup_idempotency_records

logger = logging.getLogger(__name__)

validate_auth_email_policy()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Database pool: pool_size=%d max_overflow=%d max_connections=%d pool_timeout=%ds pool_recycle=%ds",
        settings.db_pool_size,
        settings.db_max_overflow,
        settings.db_pool_size + settings.db_max_overflow,
        settings.db_pool_timeout,
        settings.db_pool_recycle,
    )
    if check_database(engine):
        db = SessionLocal()
        try:
            counts = cleanup_idempotency_records(db)
            logger.info(
                "Idempotency cleanup on startup: %d completed, %d stale in_progress deleted",
                counts["completed_deleted"],
                counts["stale_in_progress_deleted"],
            )
        except Exception:
            logger.exception("Idempotency cleanup on startup failed")
        finally:
            db.close()
    else:
        logger.warning("Database unavailable on startup; skipping idempotency cleanup")
    yield


app = FastAPI(title="Inventory & Billing API", version="1.0.0", lifespan=lifespan)

_PASSWORD_POLICY_FIELDS = frozenset({"password", "new_password"})


@app.exception_handler(RequestValidationError)
async def password_policy_validation_handler(request: Request, exc: RequestValidationError):
    for err in exc.errors():
        loc = err.get("loc", ())
        if loc and loc[-1] in _PASSWORD_POLICY_FIELDS:
            msg = err.get("msg", "Invalid password")
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
            return JSONResponse(status_code=400, content={"detail": msg})
    return await request_validation_exception_handler(request, exc)

_cors_origins = parse_cors_origins(settings.cors_origins)
logger.info("CORS allow_origins: %s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    if check_database(engine):
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "database": "ok"},
        )
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "database": "unavailable"},
    )
