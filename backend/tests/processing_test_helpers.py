"""Shared helpers for processing service unit tests."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.entities import BagType, BookSettings, InventoryOwnerType, ProcessingInputSource

PROPORTIONAL_ALLOCATION = {"output_allocation_mode": "proportional"}


def bag_type_loose(bag_type_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(id=bag_type_id, is_loose=True, weight_per_bag_kg=Decimal("0"))


def bag_type_50kg(bag_type_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=bag_type_id, is_loose=False, weight_per_bag_kg=Decimal("50"))


def bag_type_15kg(bag_type_id: int = 3) -> SimpleNamespace:
    return SimpleNamespace(id=bag_type_id, is_loose=False, weight_per_bag_kg=Decimal("15"))


def book_settings_stub() -> SimpleNamespace:
    return SimpleNamespace(
        powder_product_id=None,
        powder_brand_id=None,
        powder_location_id=None,
        powder_bag_type_id=None,
    )


def stored_input_lines_from_batches(job) -> list[SimpleNamespace]:
    lines: list[SimpleNamespace] = []
    for batch in getattr(job, "batches", []) or []:
        for ln in getattr(batch, "input_lines", []) or []:
            owner_type = getattr(ln, "owner_type", InventoryOwnerType.owned)
            lines.append(
                SimpleNamespace(
                    quantity_kg=ln.quantity_kg,
                    owner_type=owner_type,
                    customer_id=getattr(ln, "customer_id", None),
                    input_source=getattr(ln, "input_source", ProcessingInputSource.fresh),
                )
            )
    return lines


def _stmt_targets_login_rate_limit(statement) -> bool:
    text = str(statement).lower()
    return "login_rate_limit" in text


def _stmt_targets_user(statement) -> bool:
    text = str(statement).lower()
    return " users" in text or "users." in text or text.strip().startswith("select users")


def mock_db_scalar_auth(db: MagicMock, *, user=None) -> None:
    """Route db.scalar for login rate-limit vs user lookups (signup lockdown API tests)."""

    def _scalar(statement):
        if _stmt_targets_login_rate_limit(statement):
            return None
        if _stmt_targets_user(statement):
            return user
        return None

    db.scalar.side_effect = _scalar


def _stmt_targets_processing_input_line(statement) -> bool:
    text = str(statement).lower()
    return "processing_input_line" in text or "processinginputline" in text


def mock_db_stored_input_lines(db: MagicMock, *, job=None, lines: list | None = None) -> None:
    """Route db.scalars for stored ProcessingInputLine queries (mock unit tests)."""
    stored = list(lines) if lines is not None else stored_input_lines_from_batches(job)
    prior_get = db.get.side_effect

    def _get(model, pk):
        if prior_get is not None:
            return prior_get(model, pk)
        return None

    db.get.side_effect = _get

    def _scalars(statement):
        result = MagicMock()
        if _stmt_targets_processing_input_line(statement):
            result.all.return_value = stored
        else:
            result.all.return_value = []
        return result

    db.scalars = MagicMock(side_effect=_scalars)


def mock_db_bag_types(db, bag_types: dict[int, SimpleNamespace]) -> None:
    """Route db.get(BagType, id) and BookSettings; db.scalars for powder brand lookup."""

    def _get(model, pk):
        if model is BagType:
            return bag_types.get(pk)
        if model is BookSettings and pk == 1:
            return book_settings_stub()
        return None

    db.get.side_effect = _get

    def _scalars(statement):
        result = MagicMock()
        result.all.return_value = []
        return result

    db.scalars = MagicMock(side_effect=_scalars)


def balance_return_batch(return_kg: Decimal) -> SimpleNamespace:
    return SimpleNamespace(
        input_lines=[],
        output_lines=[],
        balance_return_lines=[SimpleNamespace(quantity_kg=return_kg)],
        dust_kg=Decimal("0"),
        stone_kg=Decimal("0"),
        sack_weight_waste_kg=Decimal("0"),
        miscellaneous_waste_kg=Decimal("0"),
    )


def fresh_and_return_batch(fresh_kg: Decimal, return_kg: Decimal) -> SimpleNamespace:
    bt = bag_type_50kg()
    return SimpleNamespace(
        input_lines=[
            SimpleNamespace(
                quantity_kg=fresh_kg,
                bag_count=int(fresh_kg / Decimal("50")),
                input_source=ProcessingInputSource.fresh,
                bag_type=bt,
                owner_type=InventoryOwnerType.owned,
            )
        ],
        output_lines=[],
        balance_return_lines=[SimpleNamespace(quantity_kg=return_kg)],
        dust_kg=Decimal("0"),
        stone_kg=Decimal("0"),
        sack_weight_waste_kg=Decimal("0"),
        miscellaneous_waste_kg=Decimal("0"),
    )


def fresh_input_batch(quantity_kg: Decimal) -> SimpleNamespace:
    return SimpleNamespace(
        input_lines=[
            SimpleNamespace(
                quantity_kg=quantity_kg,
                input_source=ProcessingInputSource.fresh,
                owner_type=InventoryOwnerType.owned,
            )
        ],
        output_lines=[],
        balance_return_lines=[],
        dust_kg=Decimal("0"),
        stone_kg=Decimal("0"),
        sack_weight_waste_kg=Decimal("0"),
        miscellaneous_waste_kg=Decimal("0"),
    )
