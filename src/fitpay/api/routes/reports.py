from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from fitpay.api.deps import Admin, SessionDep, SettingsDep, TodayDep
from fitpay.billing import ClientStatus
from fitpay.schemas import ClientSummary, MonthRevenue
from fitpay.services import list_clients, payments_csv, revenue_by_month

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Admin])


@router.get("/revenue", response_model=list[MonthRevenue])
def revenue(session: SessionDep, year: int | None = None) -> list[MonthRevenue]:
    """Completed payments totalled per month."""
    return revenue_by_month(session, year=year)


@router.get("/overdue", response_model=list[ClientSummary])
def overdue(session: SessionDep, settings: SettingsDep, today: TodayDep) -> list[ClientSummary]:
    return list_clients(session, today=today, settings=settings, status=ClientStatus.OVERDUE)


@router.get("/payments.csv", response_class=PlainTextResponse)
def payments_export(session: SessionDep) -> PlainTextResponse:
    return PlainTextResponse(
        payments_csv(session),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="payments.csv"'},
    )
