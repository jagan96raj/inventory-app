"""Apply Spec v3 enum/status migration directly (if alembic upgrade fails)."""
from sqlalchemy import create_engine, text

from app.config import settings

SQL = """
UPDATE fulfillment_entries SET entry_type = 'deliver' WHERE entry_type = 'receive';

ALTER TYPE payment_status_enum RENAME VALUE 'pending' TO 'unpaid';
ALTER TYPE payment_status_enum RENAME VALUE 'done' TO 'paid';

ALTER TYPE delivery_status_enum RENAME VALUE 'pending' TO 'not_delivered';
ALTER TYPE delivery_status_enum RENAME VALUE 'done' TO 'delivered';

ALTER TYPE line_delivery_status_enum RENAME VALUE 'pending' TO 'not_delivered';
ALTER TYPE line_delivery_status_enum RENAME VALUE 'done' TO 'delivered';

DELETE FROM bills WHERE status = 'draft';
UPDATE bills SET status = 'finalized' WHERE status = 'confirmed';
ALTER TYPE bill_status_enum RENAME VALUE 'confirmed' TO 'finalized';

ALTER TABLE fulfillment_entries ADD COLUMN IF NOT EXISTS vehicle_no VARCHAR(50);
ALTER TABLE fulfillment_entries ADD COLUMN IF NOT EXISTS fulfilled_at TIMESTAMPTZ DEFAULT now();
UPDATE fulfillment_entries SET fulfilled_at = created_at WHERE fulfilled_at IS NULL;
"""


def main() -> None:
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        for stmt in [s.strip() for s in SQL.split(";") if s.strip()]:
            try:
                conn.execute(text(stmt))
                print("OK:", stmt[:60], "...")
            except Exception as e:
                if "already exists" in str(e).lower() or "does not exist" in str(e).lower():
                    print("SKIP:", e)
                else:
                    raise
    print("Spec v3 migration applied.")


if __name__ == "__main__":
    main()
