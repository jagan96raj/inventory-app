"""Spec v5.4 — payment void with set-off cascade.

Scenarios:
A. Cash payment void restores bill due and customer credit balance
B. Debit + set-off void cascades to opposite bill and restores balances
C. Cannot void set-off child directly
D. Cannot void already voided payment
"""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    Bill,
    BillStatus,
    BillType,
    Customer,
    Payment,
    PaymentMode,
    PaymentStatus,
)
from app.routers.payments import void_payment_endpoint
from tests.idempotency_helpers import TEST_VOID_AUTH_PASSWORD, idem_kwargs
from app.services.payments import (
    PAYMENT_ALREADY_VOIDED_MSG,
    PAYMENT_VOID_SETOFF_MSG,
    create_payment,
    void_payment,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_customer(db: Session, *, credit="10000", debit="10000") -> Customer:
    customer = Customer(
        name="Void Test Co",
        credit_balance=Decimal(credit),
        debit_balance=Decimal(debit),
    )
    db.add(customer)
    db.flush()
    return customer


def _bill(
    db: Session,
    customer: Customer,
    *,
    bill_type: BillType,
    bill_number: str,
    grand_total: str,
) -> Bill:
    bill = Bill(
        bill_number=bill_number,
        bill_type=bill_type,
        status=BillStatus.finalized,
        bill_date=date(2026, 1, 1),
        customer_id=customer.id,
        subtotal=Decimal(grand_total),
        grand_total=Decimal(grand_total),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
    )
    db.add(bill)
    db.flush()
    return bill


def _pay(db: Session, bill_id: int, amount: Decimal, mode: PaymentMode) -> Payment:
    bill = db.get(Bill, bill_id)
    return create_payment(db, bill_id, amount, mode, expected_version=bill.version if bill else 1)


def _void_pay(db: Session, bill_id: int, payment_id: int) -> Payment:
    bill = db.get(Bill, bill_id)
    return void_payment(db, payment_id, expected_version=bill.version if bill else 1)


class PaymentVoidV54Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()

    def tearDown(self):
        self.db.close()

    def test_a_cash_void_restores_due_and_credit_balance(self):
        customer = _seed_customer(self.db, credit="10000", debit="0")
        purchase = _bill(self.db, customer, bill_type=BillType.purchase, bill_number="P-000001", grand_total="10000")

        payment = _pay(self.db, purchase.id, Decimal("2000"), PaymentMode.cash)

        self.db.refresh(customer)
        self.db.refresh(purchase)
        self.assertEqual(customer.credit_balance, Decimal("8000"))
        self.assertEqual(purchase.amount_paid, Decimal("2000"))
        self.assertEqual(purchase.payment_status, PaymentStatus.partial)

        _void_pay(self.db, purchase.id, payment.id)

        self.db.refresh(customer)
        self.db.refresh(purchase)
        row = self.db.get(Payment, payment.id)
        self.assertIsNotNone(row.voided_at)
        self.assertEqual(customer.credit_balance, Decimal("10000"))
        self.assertEqual(purchase.amount_paid, Decimal("0"))
        self.assertEqual(purchase.payment_status, PaymentStatus.unpaid)

    def test_b_debit_setoff_void_cascades(self):
        customer = _seed_customer(self.db)
        purchase = _bill(self.db, customer, bill_type=BillType.purchase, bill_number="P-000002", grand_total="10000")
        sales = _bill(self.db, customer, bill_type=BillType.sales, bill_number="S-000001", grand_total="10000")

        primary = _pay(self.db, purchase.id, Decimal("10000"), PaymentMode.debit)

        self.db.refresh(customer)
        self.db.refresh(purchase)
        self.db.refresh(sales)
        self.assertEqual(customer.credit_balance, Decimal("0"))
        self.assertEqual(customer.debit_balance, Decimal("0"))
        self.assertEqual(purchase.payment_status, PaymentStatus.paid)
        self.assertEqual(sales.payment_status, PaymentStatus.paid)
        setoff = next(p for p in sales.payments if p.payment_mode == PaymentMode.setoff)

        _void_pay(self.db, purchase.id, primary.id)

        self.db.refresh(customer)
        self.db.refresh(purchase)
        self.db.refresh(sales)
        self.db.refresh(primary)
        self.db.refresh(setoff)
        self.assertIsNotNone(primary.voided_at)
        self.assertIsNotNone(setoff.voided_at)
        self.assertEqual(customer.credit_balance, Decimal("10000"))
        self.assertEqual(customer.debit_balance, Decimal("10000"))
        self.assertEqual(purchase.amount_paid, Decimal("0"))
        self.assertEqual(sales.amount_paid, Decimal("0"))
        self.assertEqual(purchase.payment_status, PaymentStatus.unpaid)
        self.assertEqual(sales.payment_status, PaymentStatus.unpaid)

    def test_c_cannot_void_setoff_child(self):
        customer = _seed_customer(self.db)
        purchase = _bill(self.db, customer, bill_type=BillType.purchase, bill_number="P-000003", grand_total="10000")
        sales = _bill(self.db, customer, bill_type=BillType.sales, bill_number="S-000002", grand_total="10000")
        _pay(self.db, purchase.id, Decimal("10000"), PaymentMode.debit)
        self.db.refresh(sales)
        setoff = next(p for p in sales.payments if p.payment_mode == PaymentMode.setoff)

        with self.assertRaises(ValueError) as ctx:
            void_payment(self.db, setoff.id, expected_version=1)
        self.assertEqual(str(ctx.exception), PAYMENT_VOID_SETOFF_MSG)

        with self.assertRaises(HTTPException) as http_ctx:
            void_payment_endpoint(
                setoff.id,
                void_password=TEST_VOID_AUTH_PASSWORD,
                db=self.db,
                **idem_kwargs(),
            )
        self.assertEqual(http_ctx.exception.status_code, 400)
        self.assertEqual(http_ctx.exception.detail, PAYMENT_VOID_SETOFF_MSG)

    def test_d_cannot_void_twice(self):
        customer = _seed_customer(self.db, credit="5000", debit="0")
        purchase = _bill(self.db, customer, bill_type=BillType.purchase, bill_number="P-000004", grand_total="5000")
        payment = _pay(self.db, purchase.id, Decimal("1000"), PaymentMode.cash)

        _void_pay(self.db, purchase.id, payment.id)

        with self.assertRaises(ValueError) as ctx:
            _void_pay(self.db, purchase.id, payment.id)
        self.assertEqual(str(ctx.exception), PAYMENT_ALREADY_VOIDED_MSG)


if __name__ == "__main__":
    unittest.main()
