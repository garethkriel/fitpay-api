from fastapi import APIRouter, status

from fitpay.api.deps import Admin, SessionDep, SettingsDep, TodayDep
from fitpay.billing import ClientStatus
from fitpay.models import Client
from fitpay.schemas import ClientDetail, ClientIn, ClientSummary, ClientUpdate, ManualPaymentIn
from fitpay.services import (
    Conflict,
    detail,
    email_taken,
    get_client,
    get_package,
    list_clients,
    record_manual_payment,
)

router = APIRouter(prefix="/clients", tags=["clients"], dependencies=[Admin])


@router.get("", response_model=list[ClientSummary])
def all_clients(
    session: SessionDep,
    settings: SettingsDep,
    today: TodayDep,
    status: ClientStatus | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> list[ClientSummary]:
    """Every client with their payment status. Clients who owe money come first."""
    return list_clients(
        session,
        today=today,
        settings=settings,
        status=status,
        search=search,
        include_archived=include_archived,
    )


@router.post("", response_model=ClientDetail, status_code=status.HTTP_201_CREATED)
def create_client(
    data: ClientIn, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> ClientDetail:
    if email_taken(session, data.email):
        raise Conflict(f"a client with email {data.email} already exists")
    if data.package_id is not None:
        get_package(session, data.package_id)
    client = Client(**data.model_dump() | {"email": data.email.lower()})
    session.add(client)
    session.commit()
    session.refresh(client)
    return detail(client, today=today, settings=settings)


@router.get("/{client_id}", response_model=ClientDetail)
def one_client(
    client_id: int, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> ClientDetail:
    return detail(get_client(session, client_id), today=today, settings=settings)


@router.patch("/{client_id}", response_model=ClientDetail)
def update_client(
    client_id: int,
    data: ClientUpdate,
    session: SessionDep,
    settings: SettingsDep,
    today: TodayDep,
) -> ClientDetail:
    client = get_client(session, client_id)
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes:
        if email_taken(session, changes["email"], except_id=client_id):
            raise Conflict(f"a client with email {changes['email']} already exists")
        changes["email"] = changes["email"].lower()
    if changes.get("package_id") is not None:
        get_package(session, changes["package_id"])
    for field, value in changes.items():
        setattr(client, field, value)
    session.commit()
    session.refresh(client)
    return detail(client, today=today, settings=settings)


@router.post(
    "/{client_id}/payments", response_model=ClientDetail, status_code=status.HTTP_201_CREATED
)
def add_payment(
    client_id: int,
    data: ManualPaymentIn,
    session: SessionDep,
    settings: SettingsDep,
    today: TodayDep,
) -> ClientDetail:
    """Record an EFT, cash or card-machine payment."""
    client = get_client(session, client_id)
    record_manual_payment(session, client, data)
    return detail(client, today=today, settings=settings)
