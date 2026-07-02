"""CORS origin parsing (Spec v12.19)."""

DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]


def parse_cors_origins(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_DEV_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]
