"""DEV ONLY — DISABLED BY DEFAULT.

Drop public schema objects and re-run migrations (local dev only).
Blocked unless ALLOW_DESTRUCTIVE_SCRIPTS=true and DESTRUCTIVE_SCRIPT_CONFIRM=I_UNDERSTAND_DELETE_DATA
in .env, and DATABASE_URL points at localhost. Never enable on production.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import settings
from app.core.destructive_guard import require_destructive_scripts_allowed


def main() -> None:
    require_destructive_scripts_allowed("reset_db.py")
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    print("Database schema reset.")

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    print("Migrations applied.")


if __name__ == "__main__":
    main()
