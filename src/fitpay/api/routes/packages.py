from fastapi import APIRouter, status
from sqlalchemy import func, select

from fitpay.api.deps import Admin, SessionDep
from fitpay.models import Package
from fitpay.schemas import PackageIn, PackageOut, PackageUpdate
from fitpay.services import Conflict, get_package

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("", response_model=list[PackageOut])
def list_packages(session: SessionDep) -> list[Package]:
    """The packages clients can buy (public)."""
    query = select(Package).where(Package.active.is_(True)).order_by(Package.price_cents)
    return list(session.scalars(query).all())


def _name_taken(session: SessionDep, name: str, except_id: int | None = None) -> bool:
    query = select(Package.id).where(func.lower(Package.name) == name.lower())
    if except_id is not None:
        query = query.where(Package.id != except_id)
    return session.scalar(query) is not None


@router.post(
    "", response_model=PackageOut, status_code=status.HTTP_201_CREATED, dependencies=[Admin]
)
def create_package(data: PackageIn, session: SessionDep) -> Package:
    if _name_taken(session, data.name):
        raise Conflict(f"a package called {data.name!r} already exists")
    package = Package(**data.model_dump())
    session.add(package)
    session.commit()
    return package


@router.patch("/{package_id}", response_model=PackageOut, dependencies=[Admin])
def update_package(package_id: int, data: PackageUpdate, session: SessionDep) -> Package:
    package = get_package(session, package_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and _name_taken(session, changes["name"], except_id=package_id):
        raise Conflict(f"a package called {changes['name']!r} already exists")
    for field, value in changes.items():
        setattr(package, field, value)
    session.commit()
    return package
