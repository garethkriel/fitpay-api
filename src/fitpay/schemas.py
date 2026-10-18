"""Request and response shapes for the API (Pydantic)."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, computed_field

from fitpay.billing import ClientStatus, format_rands
from fitpay.models import Billing, PaymentMethod, PaymentStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Packages ---------------------------------------------------------------


class PackageIn(BaseModel):
    name: Name
    description: str = ""
    price_cents: int = Field(gt=0, description="Price in cents, e.g. 120000 for R1 200.00")
    billing: Billing
    months: int = Field(default=1, ge=1, le=36, description="Months one payment covers")
    active: bool = True


class PackageUpdate(BaseModel):
    name: Name | None = None
    description: str | None = None
    price_cents: int | None = Field(default=None, gt=0)
    billing: Billing | None = None
    months: int | None = Field(default=None, ge=1, le=36)
    active: bool | None = None


class PackageOut(ORMModel):
    id: int
    name: str
    description: str
    price_cents: int
    billing: Billing
    months: int
    active: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price(self) -> str:
        return format_rands(self.price_cents)


# --- Clients ----------------------------------------------------------------


class ClientIn(BaseModel):
    name: Name
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    package_id: int | None = None
    start_date: date
    notes: str = ""


class ClientUpdate(BaseModel):
    name: Name | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    package_id: int | None = None
    start_date: date | None = None
    notes: str | None = None
    archived: bool | None = None


class ClientSummary(BaseModel):
    id: int
    name: str
    email: str
    package: str | None
    status: ClientStatus
    paid_until: date | None
    archived: bool


class PaymentOut(ORMModel):
    id: int
    client_id: int
    package_id: int | None
    amount_cents: int
    months: int
    method: PaymentMethod
    status: PaymentStatus
    reference: str
    pf_payment_id: str | None
    paid_on: date | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def amount(self) -> str:
        return format_rands(self.amount_cents)


class ClientDetail(ClientSummary):
    phone: str | None
    start_date: date
    notes: str
    payments: list[PaymentOut]


# --- Payments ---------------------------------------------------------------


class ManualPaymentIn(BaseModel):
    """A payment taken outside PayFast: EFT, cash or a card machine."""

    amount_cents: int = Field(gt=0)
    months: int = Field(default=1, ge=1, le=36)
    method: PaymentMethod = PaymentMethod.EFT
    paid_on: date
    package_id: int | None = None


# --- Checkout ---------------------------------------------------------------


class CheckoutIn(BaseModel):
    package_id: int
    first_name: Name
    last_name: Name
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)


class CheckoutOut(BaseModel):
    """Post `fields` as a form to `action_url` to send the client to PayFast."""

    action_url: str
    reference: str
    fields: dict[str, str]


# --- Reports ----------------------------------------------------------------


class MonthRevenue(BaseModel):
    month: str = Field(description="YYYY-MM")
    payments: int
    total_cents: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> str:
        return format_rands(self.total_cents)
