"""Seed default bag types: 50kg, 30kg, 25kg, Loose (skip-if-exists).

Matches POST /api/seed/bag-types in app.routers.masters (case-insensitive name check).

Usage:
    cd backend
    python scripts/seed_bag_types.py
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import BagType

SEEDS = [
    ("50kg", Decimal("50"), False),
    ("30kg", Decimal("30"), False),
    ("25kg", Decimal("25"), False),
    ("Loose", Decimal("0"), True),
]


def main() -> None:
    db = SessionLocal()
    try:
        for name, weight, is_loose in SEEDS:
            if db.scalar(
                select(BagType).where(func.lower(func.trim(BagType.name)) == name.lower())
            ):
                print(f"Skip existing: {name}")
                continue
            db.add(BagType(name=name, weight_per_bag_kg=weight, is_loose=is_loose))
            print(f"Added: {name}")
        db.commit()
        print("Bag types seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
