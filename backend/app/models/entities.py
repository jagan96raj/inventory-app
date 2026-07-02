import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MONEY = Numeric(14, 2)
KG = Numeric(14, 3)


class BillType(str, enum.Enum):
    sales = "sales"
    purchase = "purchase"


class BillStatus(str, enum.Enum):
    finalized = "finalized"
    voided = "voided"


class PaymentStatus(str, enum.Enum):
    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"


class DeliveryStatus(str, enum.Enum):
    not_delivered = "not_delivered"
    partial = "partial"
    delivered = "delivered"


class PaymentMode(str, enum.Enum):
    cash = "cash"
    bank = "bank"
    credit = "credit"
    debit = "debit"
    setoff = "setoff"


class CashBookEntryType(str, enum.Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"


class ExpenseCategoryKind(str, enum.Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"


class CashBookSourceMode(str, enum.Enum):
    cash = "cash"
    bank = "bank"


class FulfillmentType(str, enum.Enum):
    deliver = "deliver"
    return_ = "return"


class InventoryOwnerType(str, enum.Enum):
    owned = "owned"
    job_work = "job_work"


class StockSource(str, enum.Enum):
    owned = "owned"
    job_work = "job_work"


class LineChargeType(str, enum.Enum):
    product_sale = "product_sale"
    processing_charge = "processing_charge"


class CustomerPartyType(str, enum.Enum):
    internal = "internal"
    external = "external"


class UserRole(str, enum.Enum):
    owner = "owner"
    writer = "writer"
    stock_manager = "stock_manager"
    factory_manager = "factory_manager"


class JobWorkOrderStatus(str, enum.Enum):
    open = "open"
    completed = "completed"
    cancelled = "cancelled"


class JobWorkReceiptEntryType(str, enum.Enum):
    receive = "receive"
    return_ = "return"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_products_name_lower", func.lower(func.trim(product_name)), unique=True),)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_brands_name_lower", func.lower(func.trim(name)), unique=True),)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line: Mapped[str | None] = mapped_column(String(500))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    pin_code: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_locations_name_lower", func.lower(func.trim(name)), unique=True),)


class BagType(Base):
    __tablename__ = "bag_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_per_bag_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    is_loose: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_bag_types_name_lower", func.lower(func.trim(name)), unique=True),)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line: Mapped[str | None] = mapped_column(String(500))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    pin_code: Mapped[str | None] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(String(50))
    alternate_phone: Mapped[str | None] = mapped_column(String(50))
    credit_balance: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    debit_balance: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    party_type: Mapped[CustomerPartyType] = mapped_column(
        Enum(
            CustomerPartyType,
            name="customer_party_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CustomerPartyType.internal,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_customers_name_lower", func.lower(func.trim(name)), unique=True),)


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    total_quantity_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    location: Mapped[Location] = relationship()
    bag_type: Mapped[BagType] = relationship()
    customer: Mapped["Customer | None"] = relationship()

    __table_args__ = (
        Index(
            "uq_inventory_owned_tuple",
            "product_id",
            "brand_id",
            "location_id",
            "bag_type_id",
            unique=True,
            sqlite_where=text("owner_type = 'owned'"),
            postgresql_where=text("owner_type = 'owned'"),
        ),
        Index(
            "uq_inventory_job_work_tuple",
            "product_id",
            "brand_id",
            "location_id",
            "bag_type_id",
            "customer_id",
            unique=True,
            sqlite_where=text("owner_type = 'job_work'"),
            postgresql_where=text("owner_type = 'job_work'"),
        ),
        CheckConstraint("bag_count >= 0", name="ck_inventory_bag_count_non_negative"),
        CheckConstraint("loose_kg >= 0", name="ck_inventory_loose_kg_non_negative"),
        CheckConstraint(
            "(owner_type = 'owned' AND customer_id IS NULL) OR "
            "(owner_type = 'job_work' AND customer_id IS NOT NULL)",
            name="ck_inventory_owner_customer",
        ),
    )


class BillNumberCounter(Base):
    """Spec v12.7 — monotonic bill number sequence per bill_type."""

    __tablename__ = "bill_number_counters"

    bill_type: Mapped[BillType] = mapped_column(
        Enum(BillType, name="bill_type_enum", values_callable=lambda obj: [e.value for e in obj]),
        primary_key=True,
    )
    last_number: Mapped[int] = mapped_column(default=0, nullable=False)


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    bill_type: Mapped[BillType] = mapped_column(Enum(BillType, name="bill_type_enum"), nullable=False)
    status: Mapped[BillStatus] = mapped_column(
        Enum(BillStatus, name="bill_status_enum"), default=BillStatus.finalized, nullable=False
    )
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    adjustment: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    use_balance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"), default=PaymentStatus.unpaid, nullable=False
    )
    order_delivery_status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status_enum"), default=DeliveryStatus.not_delivered, nullable=False
    )
    balance_applied_on_confirm: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship()
    location: Mapped[Location | None] = relationship()
    lines: Mapped[list["BillLine"]] = relationship(back_populates="bill", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="bill", cascade="all, delete-orphan")


class BillLine(Base):
    __tablename__ = "bill_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    ordered_bags: Mapped[int] = mapped_column(default=0, nullable=False)
    ordered_loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    ordered_quantity_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    rate_per_kg: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    line_delivery_status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="line_delivery_status_enum"),
        default=DeliveryStatus.not_delivered,
        nullable=False,
    )
    net_delivered_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    net_received_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    net_returned_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    stock_source: Mapped[StockSource] = mapped_column(
        Enum(
            StockSource,
            name="stock_source_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=StockSource.owned,
        nullable=False,
    )
    job_work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_work_orders.id"), nullable=True
    )
    line_charge_type: Mapped[LineChargeType] = mapped_column(
        Enum(
            LineChargeType,
            name="line_charge_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=LineChargeType.product_sale,
        nullable=False,
    )

    bill: Mapped[Bill] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    bag_type: Mapped[BagType] = relationship()
    fulfillment_entries: Mapped[list["FulfillmentEntry"]] = relationship(back_populates="bill_line")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode, name="payment_mode_enum"), nullable=False)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    linked_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill: Mapped[Bill] = relationship(back_populates="payments")
    bank_account: Mapped["BankAccount | None"] = relationship(foreign_keys=[bank_account_id])
    linked_payment: Mapped["Payment | None"] = relationship(
        remote_side="Payment.id",
        foreign_keys=[linked_payment_id],
        back_populates="linked_payments",
    )
    linked_payments: Mapped[list["Payment"]] = relationship(
        back_populates="linked_payment",
    )

    __table_args__ = (
        Index("ix_payments_bank_account_id", "bank_account_id"),
    )


class FulfillmentEntry(Base):
    __tablename__ = "fulfillment_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_line_id: Mapped[int] = mapped_column(ForeignKey("bill_lines.id"), nullable=False)
    parent_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("fulfillment_entries.id"), nullable=True
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    entry_type: Mapped[FulfillmentType] = mapped_column(
        Enum(FulfillmentType, values_callable=lambda obj: [e.value for e in obj], name="fulfillment_type_enum"),
        nullable=False,
    )
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    vehicle_no: Mapped[str | None] = mapped_column(String(50))
    fulfilled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bill_line: Mapped[BillLine] = relationship(back_populates="fulfillment_entries")
    location: Mapped[Location | None] = relationship()
    parent_entry: Mapped["FulfillmentEntry | None"] = relationship(
        remote_side="FulfillmentEntry.id", foreign_keys=[parent_entry_id]
    )


class BagChange(Base):
    __tablename__ = "bag_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    from_bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    from_bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    from_loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    from_quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    quantity_loss_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    operation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location: Mapped[Location] = relationship()
    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    from_bag_type: Mapped[BagType] = relationship(foreign_keys=[from_bag_type_id])
    customer: Mapped["Customer | None"] = relationship()
    to_lines: Mapped[list["BagChangeToLine"]] = relationship(
        back_populates="bag_change", cascade="all, delete-orphan", order_by="BagChangeToLine.line_index"
    )


class BagChangeToLine(Base):
    __tablename__ = "bag_change_to_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bag_change_id: Mapped[int] = mapped_column(ForeignKey("bag_changes.id", ondelete="CASCADE"), nullable=False)
    to_bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    line_index: Mapped[int] = mapped_column(default=0, nullable=False)

    bag_change: Mapped[BagChange] = relationship(back_populates="to_lines")
    to_bag_type: Mapped[BagType] = relationship()


class ProductTransfer(Base):
    __tablename__ = "product_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    from_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    to_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    operation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    bag_type: Mapped[BagType] = relationship()
    from_location: Mapped[Location] = relationship(foreign_keys=[from_location_id])
    to_location: Mapped[Location] = relationship(foreign_keys=[to_location_id])
    customer: Mapped["Customer | None"] = relationship()


class ProcessingJobStatus(str, enum.Enum):
    open = "open"
    completed = "completed"


class ProcessingOutputAllocationMode(str, enum.Enum):
    proportional = "proportional"
    single_owner = "single_owner"


class ProcessingInputSource(str, enum.Enum):
    fresh = "fresh"
    balance_reprocess = "balance_reprocess"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    input_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    input_brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    status: Mapped[ProcessingJobStatus] = mapped_column(
        Enum(ProcessingJobStatus, name="processing_job_status_enum"),
        default=ProcessingJobStatus.open,
        nullable=False,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output_allocation_mode: Mapped[ProcessingOutputAllocationMode | None] = mapped_column(
        Enum(
            ProcessingOutputAllocationMode,
            name="processing_output_allocation_mode_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    single_allocation_owner_type: Mapped[InventoryOwnerType | None] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_constraint=False,
        ),
        nullable=True,
    )
    single_allocation_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    single_allocation_customer: Mapped["Customer | None"] = relationship(
        foreign_keys=[single_allocation_customer_id]
    )

    input_product: Mapped[Product] = relationship(foreign_keys=[input_product_id])
    input_brand: Mapped[Brand] = relationship(foreign_keys=[input_brand_id])
    batches: Mapped[list["ProcessingBatch"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ProcessingBatch.operation_at"
    )


class ProcessingBatch(Base):
    __tablename__ = "processing_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False)
    operation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dust_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    stone_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    sack_weight_waste_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    miscellaneous_waste_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    powder_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    powder_brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    powder_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    powder_bag_type_id: Mapped[int | None] = mapped_column(ForeignKey("bag_types.id"), nullable=True)
    powder_bag_count: Mapped[int | None] = mapped_column(nullable=True)
    powder_loose_kg: Mapped[Decimal | None] = mapped_column(KG, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[ProcessingJob] = relationship(back_populates="batches")
    input_lines: Mapped[list["ProcessingInputLine"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="ProcessingInputLine.line_index"
    )
    output_lines: Mapped[list["ProcessingOutputLine"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="ProcessingOutputLine.line_index"
    )
    balance_return_lines: Mapped[list["ProcessingBalanceReturnLine"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ProcessingBalanceReturnLine.line_index",
    )
    waste_allocations: Mapped[list["ProcessingWasteAllocation"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    powder_brand: Mapped["Brand | None"] = relationship(foreign_keys=[powder_brand_id])
    powder_location: Mapped["Location | None"] = relationship(foreign_keys=[powder_location_id])
    powder_bag_type: Mapped["BagType | None"] = relationship(foreign_keys=[powder_bag_type_id])


class ProcessingInputLine(Base):
    __tablename__ = "processing_input_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("processing_batches.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    line_index: Mapped[int] = mapped_column(default=0, nullable=False)
    input_source: Mapped[ProcessingInputSource] = mapped_column(
        Enum(ProcessingInputSource, name="processing_input_source_enum"),
        default=ProcessingInputSource.fresh,
        nullable=False,
    )
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    job_work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_work_orders.id"), nullable=True
    )

    batch: Mapped[ProcessingBatch] = relationship(back_populates="input_lines")
    location: Mapped[Location] = relationship()
    bag_type: Mapped[BagType] = relationship()


class ProcessingBalanceReturnLine(Base):
    __tablename__ = "processing_balance_return_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("processing_batches.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    line_index: Mapped[int] = mapped_column(default=0, nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)

    batch: Mapped[ProcessingBatch] = relationship(back_populates="balance_return_lines")
    location: Mapped[Location] = relationship()
    bag_type: Mapped[BagType] = relationship()


class ProcessingOutputLine(Base):
    __tablename__ = "processing_output_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("processing_batches.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    line_index: Mapped[int] = mapped_column(default=0, nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)

    batch: Mapped[ProcessingBatch] = relationship(back_populates="output_lines")
    brand: Mapped[Brand] = relationship()
    location: Mapped[Location] = relationship()
    bag_type: Mapped[BagType] = relationship()


class ProcessingWasteAllocation(Base):
    """Spec v14.0 — per-owner waste kg allocated from a processing batch."""

    __tablename__ = "processing_waste_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("processing_batches.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    dust_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    stone_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    sack_weight_waste_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    powder_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    miscellaneous_waste_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)

    batch: Mapped[ProcessingBatch] = relationship(back_populates="waste_allocations")
    customer: Mapped["Customer | None"] = relationship()


class JWNumberCounter(Base):
    """Spec v14.0 — monotonic JW number sequence."""

    __tablename__ = "jw_number_counters"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_number: Mapped[int] = mapped_column(default=0, nullable=False)


class JobWorkOrder(Base):
    __tablename__ = "job_work_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    job_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobWorkOrderStatus] = mapped_column(
        Enum(
            JobWorkOrderStatus,
            name="job_work_order_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=JobWorkOrderStatus.open,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship()
    lines: Mapped[list["JobWorkLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="JobWorkLine.line_index"
    )


class JobWorkLine(Base):
    __tablename__ = "job_work_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("job_work_orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    ordered_bags: Mapped[int] = mapped_column(default=0, nullable=False)
    ordered_loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    ordered_quantity_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    received_bags: Mapped[int] = mapped_column(default=0, nullable=False)
    received_loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    received_quantity_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    returned_bags: Mapped[int] = mapped_column(default=0, nullable=False)
    returned_loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    returned_quantity_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    line_index: Mapped[int] = mapped_column(default=0, nullable=False)

    order: Mapped[JobWorkOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    bag_type: Mapped[BagType] = relationship()
    receipts: Mapped[list["JobWorkReceipt"]] = relationship(
        back_populates="line", cascade="all, delete-orphan"
    )


class JobWorkReceipt(Base):
    __tablename__ = "job_work_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("job_work_lines.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    vehicle_no: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    entry_type: Mapped[JobWorkReceiptEntryType] = mapped_column(
        Enum(
            JobWorkReceiptEntryType,
            name="job_work_receipt_entry_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=JobWorkReceiptEntryType.receive,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line: Mapped[JobWorkLine] = relationship(back_populates="receipts")
    location: Mapped[Location] = relationship()

    __table_args__ = (
        Index("ix_jw_receipts_line_entry_at", "line_id", "entry_type", "received_at"),
    )


class StockDisposal(Base):
    __tablename__ = "stock_disposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    owner_type: Mapped[InventoryOwnerType] = mapped_column(
        Enum(
            InventoryOwnerType,
            name="inventory_owner_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=InventoryOwnerType.owned,
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    bag_count: Mapped[int] = mapped_column(default=0, nullable=False)
    loose_kg: Mapped[Decimal] = mapped_column(KG, default=0, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(KG, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    operation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location: Mapped[Location] = relationship()
    product: Mapped[Product] = relationship()
    brand: Mapped[Brand] = relationship()
    bag_type: Mapped[BagType] = relationship()
    customer: Mapped["Customer | None"] = relationship()


class IdempotencyStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    route_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus, name="idempotency_status"),
        nullable=False,
        server_default=IdempotencyStatus.completed.value,
    )
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),
    )


class AuditEvent(Base):
    """Spec v16.0.5 — append-only central audit trail for sensitive mutations."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    entity_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_events_created_at", created_at.desc()),
        Index("ix_audit_events_user_id", user_id),
        Index("ix_audit_events_action", action),
        Index("ix_audit_events_entity_type", entity_type),
        Index("ix_audit_events_entity_type_id", entity_type, entity_id),
    )


class LoginEvent(Base):
    """Spec v16.0.6 — append-only sign-in attempt history."""

    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_login_events_created_at", created_at.desc()),
        Index("ix_login_events_email", email),
        Index("ix_login_events_user_id", user_id),
        Index("ix_login_events_success", success),
    )


class BankAccount(Base):
    """Spec v12.21 — bank account master used by payments and cash book entries."""

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number_last4: Mapped[str | None] = mapped_column(String(4))
    ifsc: Mapped[str | None] = mapped_column(String(32))
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    opening_balance_at: Mapped[date] = mapped_column(Date, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_bank_accounts_name_lower", func.lower(func.trim(name)), unique=True),
        CheckConstraint("opening_balance >= 0", name="ck_bank_accounts_opening_non_negative"),
    )


class ExpenseCategory(Base):
    """Spec v12.21 — categories for cash book entries (expense / income / transfer)."""

    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[ExpenseCategoryKind] = mapped_column(
        Enum(
            ExpenseCategoryKind,
            name="expense_category_kind_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_expense_categories_kind", "kind"),
        Index("ix_expense_categories_active_name_lower", func.lower(func.trim(name))),
    )


class CashBookEntry(Base):
    """Spec v12.21 — non-bill money movements tracked in the cash book."""

    __tablename__ = "cash_book_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_type: Mapped[CashBookEntryType] = mapped_column(
        Enum(
            CashBookEntryType,
            name="cash_book_entry_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    reference_no: Mapped[str | None] = mapped_column(String(100))
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"), nullable=True)
    source_payment_mode: Mapped[CashBookSourceMode | None] = mapped_column(
        Enum(
            CashBookSourceMode,
            name="cash_book_source_mode_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    source_bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    dest_payment_mode: Mapped[CashBookSourceMode | None] = mapped_column(
        Enum(
            CashBookSourceMode,
            name="cash_book_dest_mode_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    dest_bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped["ExpenseCategory"] = relationship()
    bill: Mapped["Bill | None"] = relationship()
    source_bank_account: Mapped["BankAccount | None"] = relationship(foreign_keys=[source_bank_account_id])
    dest_bank_account: Mapped["BankAccount | None"] = relationship(foreign_keys=[dest_bank_account_id])

    __table_args__ = (
        Index("ix_cash_book_entry_date", "entry_date"),
        Index("ix_cash_book_entry_type", "entry_type"),
        Index("ix_cash_book_category_id", "category_id"),
        Index("ix_cash_book_source_bank_id", "source_bank_account_id"),
        Index("ix_cash_book_dest_bank_id", "dest_bank_account_id"),
        Index("ix_cash_book_bill_id", "bill_id"),
        Index("ix_cash_book_voided_at", "voided_at"),
        CheckConstraint("amount > 0", name="ck_cash_book_amount_positive"),
    )


class BookSettings(Base):
    """Spec v12.21 — singleton row (id=1) for book-wide settings (cash opening)."""

    __tablename__ = "book_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    cash_opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=0, nullable=False)
    cash_opening_balance_at: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    powder_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    powder_brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    powder_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    powder_bag_type_id: Mapped[int | None] = mapped_column(ForeignKey("bag_types.id"), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_address_line: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    powder_product: Mapped["Product | None"] = relationship(foreign_keys=[powder_product_id])
    powder_brand: Mapped["Brand | None"] = relationship(foreign_keys=[powder_brand_id])
    powder_location: Mapped["Location | None"] = relationship(foreign_keys=[powder_location_id])
    powder_bag_type: Mapped["BagType | None"] = relationship(foreign_keys=[powder_bag_type_id])

    __table_args__ = (
        CheckConstraint("cash_opening_balance >= 0", name="ck_book_settings_cash_opening_non_negative"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    picture_url: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[UserRole | None] = mapped_column(
        Enum(
            UserRole,
            name="user_role_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_otp_hash: Mapped[str | None] = mapped_column(String(64))
    login_otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_otp_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_plain: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_revoked_tokens_jti", "jti"),
        Index("ix_revoked_tokens_expires_at", "expires_at"),
    )


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_login_rate_limits_email", "email", unique=True),)
