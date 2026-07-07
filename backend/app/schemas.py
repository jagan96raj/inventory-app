from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.time import business_today


def _business_date_not_future(v: date | None) -> date | None:
    if v is None:
        return None
    if v > business_today():
        raise ValueError("Date cannot be in the future")
    return v
from app.core.password_policy import validate_new_password_field
from app.models.entities import (
    BillType,
    CashBookEntryType,
    CashBookSourceMode,
    ExpenseCategoryKind,
    FulfillmentType,
    PaymentMode,
    StockSource,
)

T = TypeVar("T")


class PageOut(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ProductCreate(BaseModel):
    product_name: str

    @field_validator("product_name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()


class ProductOut(BaseModel):
    id: int
    product_name: str

    model_config = {"from_attributes": True}


class BrandCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()


class BrandOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class LocationCreate(BaseModel):
    name: str
    address_line: str | None = None
    district: str | None = None
    state: str | None = None
    pin_code: str | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("address_line", "district", "state", "pin_code")
    @classmethod
    def trim_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class LocationOut(BaseModel):
    id: int
    name: str
    address_line: str | None
    district: str | None
    state: str | None
    pin_code: str | None

    model_config = {"from_attributes": True}


class BagTypeCreate(BaseModel):
    name: str
    weight_per_bag_kg: Decimal = Field(..., ge=0)
    is_loose: bool = False

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()


class BagTypeOut(BaseModel):
    id: int
    name: str
    weight_per_bag_kg: Decimal
    is_loose: bool

    model_config = {"from_attributes": True}


class CustomerBase(BaseModel):
    name: str
    address_line: str | None = None
    district: str | None = None
    state: str | None = None
    pin_code: str | None = None
    phone: str | None = None
    alternate_phone: str | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("address_line", "district", "state", "pin_code", "phone", "alternate_phone")
    @classmethod
    def trim_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class CustomerCreate(CustomerBase):
    credit_balance: Decimal = Field(default=Decimal("0"), ge=0)
    debit_balance: Decimal = Field(default=Decimal("0"), ge=0)


class CustomerUpdate(CustomerBase):
    pass


class CustomerOut(BaseModel):
    id: int
    name: str
    address_line: str | None
    district: str | None
    state: str | None
    pin_code: str | None
    phone: str | None
    alternate_phone: str | None
    credit_balance: Decimal
    debit_balance: Decimal
    party_type: Literal["internal", "external"] = "internal"

    model_config = {"from_attributes": True}


class InventoryCreate(BaseModel):
    product_id: int
    brand_id: int
    location_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class InventoryUsageLinkOut(BaseModel):
    key: str
    label: str
    count: int
    hint: str | None = None


class InventoryUsageOut(BaseModel):
    inventory_id: int
    links: list[InventoryUsageLinkOut]
    has_activity: bool


class InventoryUpdate(BaseModel):
    """Reserved for future non-quantity metadata; quantities are not editable."""

    model_config = {"extra": "forbid"}


class InventoryOut(BaseModel):
    id: int
    product_id: int
    brand_id: int
    location_id: int
    bag_type_id: int
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    customer_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    total_quantity_kg: Decimal
    product_name: str | None = None
    brand_name: str | None = None
    location_name: str | None = None
    location_address_line: str | None = None
    location_district: str | None = None
    location_state: str | None = None
    location_pin_code: str | None = None
    bag_type_name: str | None = None

    model_config = {"from_attributes": True}


class BillLineIn(BaseModel):
    product_id: int
    brand_id: int
    bag_type_id: int
    ordered_bags: int = Field(0, ge=0)
    ordered_loose_kg: Decimal = Field(Decimal("0"), ge=0)
    rate_per_kg: Decimal = Field(..., ge=0)
    stock_source: Literal["owned", "job_work"] = "owned"
    job_work_order_id: int | None = None
    line_charge_type: Literal["product_sale", "processing_charge"] = "product_sale"


class BillLineOut(BaseModel):
    id: int
    product_id: int
    brand_id: int
    bag_type_id: int
    ordered_bags: int
    ordered_loose_kg: Decimal
    ordered_quantity_kg: Decimal
    rate_per_kg: Decimal
    line_total: Decimal
    line_delivery_status: str
    net_delivered_kg: Decimal
    net_received_kg: Decimal
    net_returned_kg: Decimal
    bags_purchased: int | None = None
    bags_sold: int | None = None
    bags_delivered: int | None = None
    quantity_kg: Decimal | None = None
    delivered_quantity_kg: Decimal | None = None
    product_name: str | None = None
    brand_name: str | None = None
    bag_type_name: str | None = None
    is_loose: bool | None = None
    remaining_kg: Decimal | None = None
    stock_source: Literal["owned", "job_work"] = "owned"
    job_work_order_id: int | None = None
    line_charge_type: Literal["product_sale", "processing_charge"] = "product_sale"

    model_config = {"from_attributes": True}


class BillFinalizeCreate(BaseModel):
    bill_type: BillType
    customer_id: int
    location_id: int | None = None
    bill_date: date | None = None
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    adjustment: Decimal = Field(Decimal("0"), ge=0)
    lines: list[BillLineIn] = Field(min_length=1)

    @field_validator("bill_date")
    @classmethod
    def bill_date_not_future(cls, v: date | None) -> date | None:
        if v is None:
            return None
        if v > business_today():
            raise ValueError("Bill date cannot be in the future")
        return v

    @model_validator(mode="after")
    def validate_location_for_bill_type(self) -> "BillFinalizeCreate":
        if self.bill_type == BillType.sales and self.location_id is None:
            raise ValueError("location_id is required for sales bills")
        return self


class BillEditLineIn(BaseModel):
    id: int
    ordered_bags: int | None = Field(default=None, ge=0)
    ordered_loose_kg: Decimal | None = Field(default=None, ge=0)
    rate_per_kg: Decimal | None = Field(default=None, ge=0)


class BillEditFinalized(BaseModel):
    expected_version: int | None = None
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    adjustment: Decimal | None = Field(default=None, ge=0)
    lines: list[BillEditLineIn] | None = None


class BillListItemOut(BaseModel):
    id: int
    bill_number: str
    bill_type: BillType
    bill_date: date
    customer_id: int
    customer_name: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    grand_total: Decimal
    final_payable: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    due_amount: Decimal
    payment_status: str
    order_delivery_status: str
    version: int


class BillsListSummaryOut(BaseModel):
    total_count: int
    unpaid_count: int
    total_due: Decimal
    pending_delivery_count: int


class BillsPageOut(BaseModel):
    items: list[BillListItemOut]
    total: int
    limit: int
    offset: int
    summary: BillsListSummaryOut


class BillOut(BaseModel):
    id: int
    bill_number: str
    bill_type: BillType
    status: str
    bill_date: date
    customer_id: int
    location_id: int | None = None
    discount_percent: Decimal
    discount_amount: Decimal
    adjustment: Decimal
    total_amount: Decimal
    final_payable: Decimal
    subtotal: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    payment_status: str
    order_delivery_status: str
    version: int
    customer_name: str | None = None
    customer_address_line: str | None = None
    customer_district: str | None = None
    customer_state: str | None = None
    customer_pin_code: str | None = None
    customer_phone: str | None = None
    location_name: str | None = None
    lines: list[BillLineOut] = []
    due_amount: Decimal | None = None
    amount_due: Decimal | None = None
    customer_credit_balance: Decimal | None = None
    customer_debit_balance: Decimal | None = None
    opposite_due_total: Decimal | None = None
    payments: list["PaymentOut"] = []

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    bill_id: int
    amount: Decimal = Field(..., gt=0)
    payment_mode: PaymentMode
    bank_account_id: int | None = None
    expected_version: int | None = None
    paid_date: date | None = None

    @field_validator("paid_date")
    @classmethod
    def paid_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)

    @field_validator("payment_mode")
    @classmethod
    def reject_setoff_mode(cls, v: PaymentMode) -> PaymentMode:
        if v == PaymentMode.setoff:
            raise ValueError("Set-off payments cannot be created directly")
        return v


class PaymentOut(BaseModel):
    id: int
    bill_id: int
    amount: Decimal
    payment_mode: PaymentMode
    bank_account_id: int | None = None
    bank_account_name: str | None = None
    paid_at: datetime
    voided_at: datetime | None = None
    linked_payment_id: int | None = None
    bill_number: str | None = None
    customer_name: str | None = None
    bill_type: str | None = None
    grand_total: Decimal | None = None
    amount_paid: Decimal | None = None
    amount_due: Decimal | None = None
    bill_version: int | None = None
    linked_payments: list["PaymentOut"] = []

    model_config = {"from_attributes": True}


class SetoffAllocationPreview(BaseModel):
    bill_id: int
    bill_number: str
    amount: Decimal


class SetoffPreviewOut(BaseModel):
    bill_id: int
    amount: Decimal
    payment_mode: PaymentMode
    opposite_due_total: Decimal
    max_amount: Decimal
    allocations: list[SetoffAllocationPreview]


class FulfillmentBillEventLineIn(BaseModel):
    bill_line_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class FulfillmentBillEventCreate(BaseModel):
    bill_id: int
    entry_type: FulfillmentType
    vehicle_no: str | None = None
    location_id: int | None = None
    expected_version: int | None = None
    lines: list[FulfillmentBillEventLineIn] = Field(min_length=1)
    fulfilled_date: date | None = None

    @field_validator("fulfilled_date")
    @classmethod
    def fulfilled_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)


class FulfillmentCreate(BaseModel):
    bill_line_id: int
    entry_type: FulfillmentType
    quantity_kg: Decimal = Field(..., ge=0)
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    location_id: int | None = None
    parent_entry_id: int | None = None
    notes: str | None = None
    vehicle_no: str | None = None
    expected_version: int | None = None
    fulfilled_date: date | None = None

    @field_validator("fulfilled_date")
    @classmethod
    def fulfilled_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)


class FulfillmentOut(BaseModel):
    id: int
    bill_line_id: int
    entry_type: FulfillmentType
    quantity_kg: Decimal
    bag_count: int
    loose_kg: Decimal
    location_id: int | None = None
    location_name: str | None = None
    parent_entry_id: int | None = None
    notes: str | None
    vehicle_no: str | None = None
    fulfilled_at: datetime | None = None
    created_at: datetime
    voided_at: datetime | None = None

    model_config = {"from_attributes": True}


class FulfillmentAuditOut(FulfillmentOut):
    bill_id: int
    bill_number: str
    bill_type: BillType
    bill_version: int
    customer_name: str | None = None
    product_name: str | None = None
    brand_name: str | None = None
    bag_type_name: str | None = None
    is_loose: bool = False
    bill_location_name: str | None = None
    stock_source: StockSource | None = None


class BalancePreview(BaseModel):
    delta_due: str
    credit_balance_change: str
    debit_balance_change: str
    new_credit_balance: str
    new_debit_balance: str


class BagChangeToLineIn(BaseModel):
    to_bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class StockOwnerMixin(BaseModel):
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None

    @model_validator(mode="after")
    def validate_stock_owner(self) -> "StockOwnerMixin":
        if self.owner_type == "job_work" and self.customer_id is None:
            raise ValueError("customer_id is required for job_work stock")
        if self.owner_type == "owned" and self.customer_id is not None:
            raise ValueError("customer_id must be null for owned stock")
        return self


class BagChangeCreate(StockOwnerMixin):
    location_id: int
    product_id: int
    brand_id: int
    from_bag_type_id: int
    from_bag_count: int = Field(0, ge=0)
    from_loose_kg: Decimal = Field(Decimal("0"), ge=0)
    quantity_loss_kg: Decimal = Field(Decimal("0"), ge=0)
    to_lines: list[BagChangeToLineIn] = Field(min_length=1)
    notes: str | None = None


class BagChangeToLineOut(BaseModel):
    id: int
    to_bag_type_id: int
    to_bag_type_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    line_index: int

    model_config = {"from_attributes": True}


class BagChangeOut(BaseModel):
    id: int
    location_id: int
    location_name: str | None = None
    product_id: int
    product_name: str | None = None
    brand_id: int
    brand_name: str | None = None
    from_bag_type_id: int
    from_bag_type_name: str | None = None
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    customer_name: str | None = None
    from_bag_count: int
    from_loose_kg: Decimal
    from_quantity_kg: Decimal
    quantity_loss_kg: Decimal
    operation_at: datetime
    voided_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    to_lines: list[BagChangeToLineOut] = []

    model_config = {"from_attributes": True}


class ProductTransferCreate(StockOwnerMixin):
    product_id: int
    brand_id: int
    bag_type_id: int
    from_location_id: int
    to_location_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def locations_must_differ(self) -> "ProductTransferCreate":
        if self.from_location_id == self.to_location_id:
            raise ValueError("from_location_id and to_location_id must differ")
        return self


class ProductTransferOut(BaseModel):
    id: int
    product_id: int
    product_name: str | None = None
    brand_id: int
    brand_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    from_location_id: int
    from_location_name: str | None = None
    to_location_id: int
    to_location_name: str | None = None
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    customer_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    operation_at: datetime
    voided_at: datetime | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StockDisposalCreate(StockOwnerMixin):
    location_id: int
    product_id: int
    brand_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    reason: str | None = None
    notes: str | None = None


class StockDisposalOut(BaseModel):
    id: int
    location_id: int
    location_name: str | None = None
    product_id: int
    product_name: str | None = None
    brand_id: int
    brand_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    customer_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    reason: str | None = None
    notes: str | None = None
    operation_at: datetime
    voided_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProcessingInputLineIn(BaseModel):
    location_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    input_source: Literal["fresh", "balance_reprocess"] = "fresh"
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    job_work_order_id: int | None = None

    @model_validator(mode="after")
    def job_work_requires_customer(self) -> "ProcessingInputLineIn":
        if self.owner_type == "job_work" and self.customer_id is None:
            raise ValueError("customer_id is required when owner_type is job_work")
        return self


class ProcessingBalanceReturnLineIn(BaseModel):
    location_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class ProcessingOutputLineIn(BaseModel):
    brand_id: int
    location_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class ProcessingPowderLineIn(BaseModel):
    brand_id: int
    location_id: int
    bag_type_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)


class ProcessingBatchSubmit(BaseModel):
    input_lines: list[ProcessingInputLineIn] = []
    output_lines: list[ProcessingOutputLineIn] = []
    balance_return_lines: list[ProcessingBalanceReturnLineIn] = []
    dust_kg: Decimal = Field(Decimal("0"), ge=0)
    stone_kg: Decimal = Field(Decimal("0"), ge=0)
    sack_weight_waste_kg: Decimal = Field(Decimal("0"), ge=0)
    powder_kg: Decimal = Field(Decimal("0"), ge=0)
    powder_line: ProcessingPowderLineIn | None = None
    miscellaneous_waste_kg: Decimal = Field(Decimal("0"), ge=0)
    output_allocation_mode: Literal["proportional", "single_owner"] | None = None
    single_allocation_owner_type: Literal["owned", "job_work"] | None = None
    single_allocation_customer_id: int | None = None

    @model_validator(mode="after")
    def validate_single_allocation_owner(self) -> "ProcessingBatchSubmit":
        if self.single_allocation_owner_type == "owned" and self.single_allocation_customer_id is not None:
            raise ValueError("single_allocation_customer_id must be null when owner is owned")
        if self.single_allocation_owner_type == "job_work" and self.single_allocation_customer_id is None:
            raise ValueError("single_allocation_customer_id is required when owner is job_work")
        return self

    @model_validator(mode="after")
    def validate_powder_input(self) -> "ProcessingBatchSubmit":
        if self.powder_line is not None and self.powder_kg > 0:
            raise ValueError("Send powder_line or powder_kg, not both")
        return self


class ProcessingJobCreate(BaseModel):
    input_product_id: int
    input_brand_id: int


class ProcessingInputLineOut(BaseModel):
    id: int
    location_id: int
    location_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    bag_type_is_loose: bool | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    line_index: int
    input_source: Literal["fresh", "balance_reprocess"]
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None
    job_work_order_id: int | None = None

    model_config = {"from_attributes": True}


class ProcessingBalanceReturnLineOut(BaseModel):
    id: int
    location_id: int
    location_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    line_index: int
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None

    model_config = {"from_attributes": True}


class ProcessingOutputLineOut(BaseModel):
    id: int
    brand_id: int
    brand_name: str | None = None
    location_id: int
    location_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    line_index: int
    owner_type: Literal["owned", "job_work"] = "owned"
    customer_id: int | None = None

    model_config = {"from_attributes": True}


class ProcessingWasteAllocationOut(BaseModel):
    owner_type: Literal["owned", "job_work"]
    customer_id: int | None = None
    dust_kg: Decimal
    stone_kg: Decimal
    sack_weight_waste_kg: Decimal
    powder_kg: Decimal = Decimal("0")
    miscellaneous_waste_kg: Decimal

    model_config = {"from_attributes": True}


class ProcessingBatchOut(BaseModel):
    id: int
    operation_at: datetime
    voided_at: datetime | None = None
    dust_kg: Decimal
    stone_kg: Decimal
    sack_weight_waste_kg: Decimal
    powder_kg: Decimal
    powder_brand_id: int | None = None
    powder_brand_name: str | None = None
    powder_location_id: int | None = None
    powder_location_name: str | None = None
    powder_bag_type_id: int | None = None
    powder_bag_type_name: str | None = None
    powder_bag_type_is_loose: bool | None = None
    powder_bag_count: int | None = None
    powder_loose_kg: Decimal | None = None
    miscellaneous_waste_kg: Decimal
    input_lines: list[ProcessingInputLineOut] = []
    output_lines: list[ProcessingOutputLineOut] = []
    balance_return_lines: list[ProcessingBalanceReturnLineOut] = []
    waste_allocations: list[ProcessingWasteAllocationOut] = []

    model_config = {"from_attributes": True}


class ProcessingOutputByBrandOut(BaseModel):
    brand_id: int
    brand_name: str | None = None
    quantity_kg: Decimal
    bag_count: int


class ProcessingOwnerAllocationWeightOut(BaseModel):
    owner_type: Literal["owned", "job_work"]
    customer_id: int | None = None
    customer_name: str | None = None
    input_kg: Decimal
    share_pct: Decimal


class ProcessingJobSummaryOut(BaseModel):
    total_fresh_input_kg: Decimal
    fresh_input_bags: int
    total_balance_reprocess_kg: Decimal
    total_balance_return_kg: Decimal
    net_balance_kg: Decimal
    job_available_reprocess_kg: Decimal
    output_by_brand: list[ProcessingOutputByBrandOut]
    total_waste_kg: Decimal
    total_misc_kg: Decimal
    total_loss_kg: Decimal
    batch_count: int
    in_process_kg: Decimal = Decimal("0")


class ProcessingJobListSummaryOut(BaseModel):
    batch_count: int
    total_output_kg: Decimal

    model_config = {"from_attributes": True}


class ProcessingJobListItemOut(BaseModel):
    id: int
    input_product_id: int
    input_product_name: str | None = None
    input_brand_id: int
    input_brand_name: str | None = None
    status: Literal["open", "completed"]
    opened_at: datetime
    completed_at: datetime | None = None
    batches: list[ProcessingBatchOut] = []
    summary: ProcessingJobListSummaryOut

    model_config = {"from_attributes": True}


class ProcessingInputAllowedOwnerOut(BaseModel):
    owner_type: Literal["owned", "job_work"]
    customer_id: int | None = None
    customer_name: str | None = None


class ProcessingJobOut(BaseModel):
    id: int
    input_product_id: int
    input_product_name: str | None = None
    input_brand_id: int
    input_brand_name: str | None = None
    status: Literal["open", "completed"]
    opened_at: datetime
    completed_at: datetime | None = None
    batches: list[ProcessingBatchOut] = []
    summary: ProcessingJobSummaryOut
    owner_mode: Literal["single_owner", "mixed"] = "single_owner"
    input_locked: bool = False
    input_allowed_owner: ProcessingInputAllowedOwnerOut | None = None
    has_output: bool = False
    input_rules_hint: str | None = None
    owner_allocation_weights: list[ProcessingOwnerAllocationWeightOut] = []
    output_allocation_mode: Literal["proportional", "single_owner"] | None = None
    single_allocation_owner_type: Literal["owned", "job_work"] | None = None
    single_allocation_customer_id: int | None = None
    single_allocation_customer_name: str | None = None
    output_allocation_locked: bool = False
    output_allocation_hint: str | None = None

    model_config = {"from_attributes": True}


class GoogleAuthIn(BaseModel):
    id_token: str


class SignupIn(BaseModel):
    email: str
    password: str
    name: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        email = v.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_new_password_field(v)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        name = v.strip()
        return name or None


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None = None
    picture_url: str | None = None
    role: Literal["owner", "writer", "stock_manager", "factory_manager"] | None = None

    model_config = {"from_attributes": True}


class UserAdminOut(UserOut):
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    password: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    email: str
    password: str
    name: str | None = None
    role: Literal["owner", "writer", "stock_manager", "factory_manager"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_new_password_field(v)


class UserUpdate(BaseModel):
    name: str | None = None
    role: Literal["owner", "writer", "stock_manager", "factory_manager"] | None = None
    password: str | None = None
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_new_password_field(v)


class LoginOtpIn(BaseModel):
    email: str
    otp: str
    new_password: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_new_password_field(v)

    @field_validator("otp")
    @classmethod
    def normalize_otp(cls, v: str) -> str:
        code = v.strip()
        if len(code) != 6 or not code.isdigit():
            raise ValueError("Enter the 6-digit login code")
        return code


class LoginOtpOut(BaseModel):
    otp: str
    expires_at: datetime
    user_email: str
    user_name: str | None = None

class ReportStatusBucketOut(BaseModel):
    count: int
    amount: Decimal


class SalesSummaryOut(BaseModel):
    total_sales: Decimal
    bill_count: int
    total_quantity_kg: Decimal
    total_collected: Decimal
    total_due: Decimal
    avg_bill_value: Decimal
    prev_month_sales: Decimal
    mom_change_percent: Decimal | None = None


class SalesProductRowOut(BaseModel):
    product_id: int
    product_name: str
    brand_id: int | None = None
    brand_name: str | None = None
    quantity_kg: Decimal
    bag_count: int
    amount: Decimal
    share_percent: Decimal
    avg_rate_per_kg: Decimal


class SalesByProductOut(BaseModel):
    rows: list[SalesProductRowOut]
    lines_subtotal: Decimal
    bills_grand_total: Decimal
    group_by: str


class SalesCustomerRowOut(BaseModel):
    customer_id: int
    customer_name: str
    bill_count: int
    quantity_kg: Decimal
    amount: Decimal
    share_percent: Decimal


class SalesByCustomerOut(BaseModel):
    rows: list[SalesCustomerRowOut]
    total_amount: Decimal


class SalesLocationRowOut(BaseModel):
    location_id: int | None
    location_name: str
    bill_count: int
    quantity_kg: Decimal
    amount: Decimal


class SalesByLocationOut(BaseModel):
    rows: list[SalesLocationRowOut]


class SalesDailyRowOut(BaseModel):
    day: int
    bill_date: date
    amount: Decimal
    bill_count: int
    quantity_kg: Decimal


class SalesDailyOut(BaseModel):
    rows: list[SalesDailyRowOut]


class SalesCompareBucketOut(BaseModel):
    sales: Decimal
    bills: int
    kg: Decimal
    collected: Decimal


class SalesCompareChangeOut(BaseModel):
    sales: Decimal | None = None
    bills: Decimal | None = None
    kg: Decimal | None = None
    collected: Decimal | None = None


class SalesCompareOut(BaseModel):
    current: SalesCompareBucketOut
    previous: SalesCompareBucketOut
    change_percent: SalesCompareChangeOut


class SalesPaymentBreakdownOut(BaseModel):
    paid: ReportStatusBucketOut
    partial: ReportStatusBucketOut
    unpaid: ReportStatusBucketOut


class SalesDeliveryBreakdownOut(BaseModel):
    delivered: ReportStatusBucketOut
    partial: ReportStatusBucketOut
    not_delivered: ReportStatusBucketOut


class BusinessTypeSummaryOut(BaseModel):
    bill_amount: Decimal
    bill_count: int
    qty_ordered_kg: Decimal
    bags_ordered: int = 0


class BusinessSummaryOut(BaseModel):
    year: int
    month: int
    sales: BusinessTypeSummaryOut
    purchase: BusinessTypeSummaryOut


class BusinessCompareBucketOut(BaseModel):
    sales_bill_amount: Decimal
    sales_qty_ordered_kg: Decimal
    sales_bags_ordered: int = 0
    sales_bill_count: int
    purchase_bill_amount: Decimal
    purchase_qty_ordered_kg: Decimal
    purchase_bags_ordered: int = 0
    purchase_bill_count: int


class BusinessCompareChangeOut(BaseModel):
    sales_bill_amount: Decimal | None = None
    sales_qty_ordered_kg: Decimal | None = None
    sales_bags_ordered: Decimal | None = None
    sales_bill_count: Decimal | None = None
    purchase_bill_amount: Decimal | None = None
    purchase_qty_ordered_kg: Decimal | None = None
    purchase_bags_ordered: Decimal | None = None
    purchase_bill_count: Decimal | None = None


class BusinessCompareOut(BaseModel):
    current: BusinessCompareBucketOut
    previous: BusinessCompareBucketOut
    change_percent: BusinessCompareChangeOut


class DailyBillAmountRowOut(BaseModel):
    day: int
    bill_date: date
    sales_amount: Decimal
    purchase_amount: Decimal
    sales_bill_count: int
    purchase_bill_count: int


class DailyBillAmountsOut(BaseModel):
    rows: list[DailyBillAmountRowOut]


class DashboardBundleOut(BaseModel):
    summary: BusinessSummaryOut
    compare: BusinessCompareOut
    daily: DailyBillAmountsOut
    by_product: SalesByProductOut
    by_customer: SalesByCustomerOut
    by_location: SalesByLocationOut


class AuditEventOut(BaseModel):
    id: int
    user_id: int | None = None
    user_email: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    entity_label: str | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventPageOut(PageOut[AuditEventOut]):
    pass


class LoginEventOut(BaseModel):
    id: int
    email: str
    user_id: int | None = None
    success: bool
    failure_reason: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginEventPageOut(PageOut[LoginEventOut]):
    pass


# Paginated list response aliases (Spec v12.18)
class ProductPageOut(PageOut[ProductOut]):
    pass


class BrandPageOut(PageOut[BrandOut]):
    pass


class LocationPageOut(PageOut[LocationOut]):
    pass


class BagTypePageOut(PageOut[BagTypeOut]):
    pass


class CustomerPageOut(PageOut[CustomerOut]):
    pass


class InventoryPageOut(PageOut[InventoryOut]):
    pass


class PaymentPageOut(PageOut[PaymentOut]):
    pass


class BagChangePageOut(PageOut[BagChangeOut]):
    pass


class ProductTransferPageOut(PageOut[ProductTransferOut]):
    pass


class StockDisposalPageOut(PageOut[StockDisposalOut]):
    pass


class ProcessingJobPageOut(PageOut[ProcessingJobListItemOut]):
    pass


class FulfillmentEntryPageOut(PageOut[FulfillmentOut]):
    pass


class FulfillmentAuditPageOut(PageOut[FulfillmentAuditOut]):
    pass


# ---------------------------------------------------------------------------
# Spec v12.21 — Accounts, Cash Book & Multi-Bank
# ---------------------------------------------------------------------------


class BankAccountCreate(BaseModel):
    name: str
    account_number_last4: str | None = None
    ifsc: str | None = None
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("account_number_last4")
    @classmethod
    def validate_last4(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if len(s) != 4 or not s.isdigit():
            raise ValueError("account_number_last4 must be exactly 4 digits")
        return s

    @field_validator("ifsc")
    @classmethod
    def trim_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class BankAccountUpdate(BaseModel):
    name: str | None = None
    account_number_last4: str | None = None
    ifsc: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("name cannot be empty")
        return s

    @field_validator("account_number_last4")
    @classmethod
    def validate_last4(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if len(s) != 4 or not s.isdigit():
            raise ValueError("account_number_last4 must be exactly 4 digits")
        return s

    @field_validator("ifsc")
    @classmethod
    def trim_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class BankAccountOut(BaseModel):
    id: int
    name: str
    account_number_last4: str | None = None
    ifsc: str | None = None
    opening_balance: Decimal
    opening_balance_at: date
    is_default: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BankAccountBalanceOut(BankAccountOut):
    balance: Decimal


class BankAccountPageOut(PageOut[BankAccountBalanceOut]):
    pass


class ExpenseCategoryCreate(BaseModel):
    name: str
    kind: ExpenseCategoryKind

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("kind")
    @classmethod
    def reject_transfer_kind(cls, v: ExpenseCategoryKind) -> ExpenseCategoryKind:
        if v == ExpenseCategoryKind.transfer:
            raise ValueError("Transfer categories are system-managed")
        return v


class ExpenseCategoryUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("name cannot be empty")
        return s


class ExpenseCategoryOut(BaseModel):
    id: int
    name: str
    kind: ExpenseCategoryKind
    is_system: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExpenseCategoryPageOut(PageOut[ExpenseCategoryOut]):
    pass


class CashBookEntryCreate(BaseModel):
    entry_type: CashBookEntryType
    category_id: int
    amount: Decimal = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=500)
    reference_no: str | None = Field(default=None, max_length=100)
    bill_id: int | None = None
    source_payment_mode: CashBookSourceMode | None = None
    source_bank_account_id: int | None = None
    dest_payment_mode: CashBookSourceMode | None = None
    dest_bank_account_id: int | None = None
    entry_date: date | None = None

    @field_validator("entry_date")
    @classmethod
    def entry_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)

    @field_validator("description", "reference_no")
    @classmethod
    def trim_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @model_validator(mode="after")
    def validate_modes(self) -> "CashBookEntryCreate":
        if self.entry_type in (CashBookEntryType.expense, CashBookEntryType.income):
            if self.source_payment_mode is None:
                raise ValueError("source_payment_mode is required for expense/income entries")
            if self.dest_payment_mode is not None or self.dest_bank_account_id is not None:
                raise ValueError("dest_* fields not allowed for expense/income entries")
        elif self.entry_type == CashBookEntryType.transfer:
            if self.source_payment_mode is None or self.dest_payment_mode is None:
                raise ValueError("transfer requires source_payment_mode and dest_payment_mode")
            if (
                self.source_payment_mode == self.dest_payment_mode == CashBookSourceMode.cash
            ):
                raise ValueError("Cash to cash transfer is not allowed")
            if (
                self.source_payment_mode == CashBookSourceMode.bank
                and self.dest_payment_mode == CashBookSourceMode.bank
                and self.source_bank_account_id is not None
                and self.dest_bank_account_id is not None
                and self.source_bank_account_id == self.dest_bank_account_id
            ):
                raise ValueError("Source and destination bank accounts must differ")
        if self.source_payment_mode == CashBookSourceMode.bank and self.source_bank_account_id is None:
            raise ValueError("source_bank_account_id is required when source is bank")
        if self.source_payment_mode == CashBookSourceMode.cash and self.source_bank_account_id is not None:
            raise ValueError("source_bank_account_id must be null when source is cash")
        if self.dest_payment_mode == CashBookSourceMode.bank and self.dest_bank_account_id is None:
            raise ValueError("dest_bank_account_id is required when destination is bank")
        if self.dest_payment_mode == CashBookSourceMode.cash and self.dest_bank_account_id is not None:
            raise ValueError("dest_bank_account_id must be null when destination is cash")
        return self


class CashBookEntryEdit(CashBookEntryCreate):
    expected_version: int | None = None


class CashBookEntryOut(BaseModel):
    id: int
    entry_type: CashBookEntryType
    category_id: int
    category_name: str | None = None
    category_kind: ExpenseCategoryKind | None = None
    amount: Decimal
    description: str | None = None
    reference_no: str | None = None
    bill_id: int | None = None
    bill_number: str | None = None
    source_payment_mode: CashBookSourceMode | None = None
    source_bank_account_id: int | None = None
    source_bank_account_name: str | None = None
    dest_payment_mode: CashBookSourceMode | None = None
    dest_bank_account_id: int | None = None
    dest_bank_account_name: str | None = None
    entry_date: date
    entry_at: datetime
    voided_at: datetime | None = None
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CashBookEntryPageOut(PageOut[CashBookEntryOut]):
    pass


class BookSettingsOut(BaseModel):
    id: int
    cash_opening_balance: Decimal
    cash_opening_balance_at: date
    updated_at: datetime
    powder_product_id: int | None = None
    powder_product_name: str | None = None
    powder_brand_id: int | None = None
    powder_brand_name: str | None = None
    powder_location_id: int | None = None
    powder_location_name: str | None = None
    powder_bag_type_id: int | None = None
    powder_bag_type_name: str | None = None
    company_name: str | None = None
    company_address_line: str | None = None
    company_phone: str | None = None

    model_config = {"from_attributes": True}


class BookSettingsUpdate(BaseModel):
    cash_opening_balance: Decimal | None = Field(None, ge=0)
    powder_product_id: int | None = None
    powder_brand_id: int | None = None
    powder_location_id: int | None = None
    powder_bag_type_id: int | None = None
    company_name: str | None = Field(None, max_length=255)
    company_address_line: str | None = Field(None, max_length=500)
    company_phone: str | None = Field(None, max_length=50)


class AccountsSummaryOut(BaseModel):
    cash_balance: Decimal
    total_bank_balance: Decimal
    total_money: Decimal
    total_customer_credit: Decimal
    total_customer_debit: Decimal
    bank_accounts: list[BankAccountBalanceOut]
    recent_entries: list[CashBookEntryOut]


class CustomerBalanceRowOut(BaseModel):
    customer_id: int
    customer_name: str
    credit_balance: Decimal
    debit_balance: Decimal
    net_balance: Decimal
    last_activity_at: datetime | None = None


class CustomerBalancePageOut(PageOut[CustomerBalanceRowOut]):
    pass


class CustomerStatementEventOut(BaseModel):
    event_at: datetime
    event_date: date
    kind: str
    description: str
    bill_id: int | None = None
    bill_number: str | None = None
    payment_id: int | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal


class CustomerStatementPageOut(PageOut[CustomerStatementEventOut]):
    customer_id: int
    customer_name: str
    current_credit_balance: Decimal
    current_debit_balance: Decimal
    current_net_balance: Decimal


class BillPickerItemOut(BaseModel):
    id: int
    bill_number: str
    bill_type: BillType
    customer_id: int | None = None
    customer_name: str | None = None
    bill_date: date
    grand_total: Decimal


class BillPickerPageOut(PageOut[BillPickerItemOut]):
    pass


class BillVoidLinkedInfoOut(BaseModel):
    bill_id: int
    can_void: bool
    block_reasons: list[str]
    linked_active_entries_count: int
    linked_active_entries_amount: Decimal


# --- Spec v14.0 Job Work ---


class JobWorkLineIn(BaseModel):
    product_id: int
    brand_id: int
    bag_type_id: int
    ordered_bags: int = Field(0, ge=0)
    ordered_loose_kg: Decimal = Field(Decimal("0"), ge=0)


class JobWorkOrderCreate(BaseModel):
    customer_id: int
    job_date: date
    notes: str | None = None
    lines: list[JobWorkLineIn]


class JobWorkReceiptOut(BaseModel):
    id: int
    line_id: int
    location_id: int
    location_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    vehicle_no: str | None = None
    notes: str | None = None
    entry_type: Literal["receive", "return"] = "receive"
    received_at: datetime
    voided_at: datetime | None = None


class JobWorkLineOut(BaseModel):
    id: int
    product_id: int
    product_name: str | None = None
    brand_id: int
    brand_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    weight_per_bag_kg: Decimal | None = None
    is_loose: bool = False
    ordered_bags: int
    ordered_loose_kg: Decimal
    ordered_quantity_kg: Decimal
    received_bags: int
    received_loose_kg: Decimal
    received_quantity_kg: Decimal
    returned_bags: int
    returned_loose_kg: Decimal
    returned_quantity_kg: Decimal
    net_received_bags: int = 0
    net_received_loose_kg: Decimal = Decimal("0")
    net_received_kg: Decimal = Decimal("0")
    remaining_receive_bags: int = 0
    remaining_receive_loose_kg: Decimal = Decimal("0")
    remaining_receive_kg: Decimal = Decimal("0")
    custody_bags: int = 0
    custody_loose_kg: Decimal = Decimal("0")
    custody_kg: Decimal = Decimal("0")
    line_index: int
    receipts: list[JobWorkReceiptOut] = []


class JobWorkOrderOut(BaseModel):
    id: int
    job_number: str
    customer_id: int
    customer_name: str | None = None
    job_date: date
    notes: str | None = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    lines: list[JobWorkLineOut] = []


class JobWorkOrderPageOut(PageOut[JobWorkOrderOut]):
    pass


class JobWorkReceiveIn(BaseModel):
    line_id: int
    location_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    vehicle_no: str | None = None
    notes: str | None = None
    received_date: date | None = None

    @field_validator("received_date")
    @classmethod
    def received_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)


class JobWorkReturnIn(BaseModel):
    line_id: int
    location_id: int
    bag_count: int = Field(0, ge=0)
    loose_kg: Decimal = Field(Decimal("0"), ge=0)
    notes: str | None = None
    received_date: date | None = None

    @field_validator("received_date")
    @classmethod
    def received_date_not_future(cls, v: date | None) -> date | None:
        return _business_date_not_future(v)


class JobWorkStatementOrderOut(BaseModel):
    job_work_order_id: int
    job_number: str
    job_date: date
    status: str
    ordered_quantity_kg: Decimal
    received_quantity_kg: Decimal
    returned_quantity_kg: Decimal
    outstanding_quantity_kg: Decimal


class JobWorkStatementOut(BaseModel):
    customer_id: int
    customer_name: str
    from_date: date | None = None
    to_date: date | None = None
    total_ordered_kg: Decimal
    total_received_kg: Decimal
    total_returned_kg: Decimal
    outstanding_in_custody_kg: Decimal
    orders: list[JobWorkStatementOrderOut] = []


class JobWorkFulfillmentReceiptOut(BaseModel):
    id: int
    line_id: int
    location_id: int
    location_name: str | None = None
    bag_count: int
    loose_kg: Decimal
    quantity_kg: Decimal
    vehicle_no: str | None = None
    notes: str | None = None
    entry_type: Literal["receive", "return"] = "receive"
    received_at: datetime
    voided_at: datetime | None = None


class JwReturnLocationOut(BaseModel):
    location_id: int
    location_name: str | None = None
    returnable_bags: int = 0
    returnable_loose_kg: Decimal = Decimal("0")
    returnable_kg: Decimal


class JobWorkFulfillmentLineOut(BaseModel):
    line_id: int
    order_id: int
    job_number: str
    customer_name: str | None = None
    product_id: int
    product_name: str | None = None
    brand_id: int
    brand_name: str | None = None
    bag_type_id: int
    bag_type_name: str | None = None
    weight_per_bag_kg: Decimal | None = None
    is_loose: bool = False
    ordered_bags: int
    ordered_loose_kg: Decimal
    received_bags: int
    received_loose_kg: Decimal = Decimal("0")
    returned_bags: int
    returned_loose_kg: Decimal = Decimal("0")
    net_received_bags: int = 0
    net_received_loose_kg: Decimal = Decimal("0")
    ordered_kg: Decimal
    received_kg: Decimal
    returned_kg: Decimal
    net_received_kg: Decimal = Decimal("0")
    remaining_receive_kg: Decimal
    remaining_receive_bags: int = 0
    remaining_receive_loose_kg: Decimal = Decimal("0")
    custody_kg: Decimal  # Deprecated alias for net_received_kg; prefer net_received_kg in UI
    custody_bags: int = 0  # Deprecated alias for net_received_bags
    custody_loose_kg: Decimal = Decimal("0")  # Deprecated alias for net_received_loose_kg
    return_locations: list[JwReturnLocationOut] = []
    receipts: list[JobWorkFulfillmentReceiptOut] = []


class JobWorkFulfillmentOrderOut(BaseModel):
    order_id: int
    job_number: str
    customer_id: int
    customer_name: str | None = None
    job_date: date
    status: str
    lines: list[JobWorkFulfillmentLineOut] = []


class JobWorkFulfillmentOrderPageOut(PageOut[JobWorkFulfillmentOrderOut]):
    pass
