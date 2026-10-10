import uuid

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.tenant import Tenant

_DEFAULT_TENANT_NAME = "default"


def get_current_tenant_id(
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
) -> uuid.UUID:
    """Resolve the active tenant.

    Auth is deferred to Stage 4; until then every request is scoped to a
    single seeded "default" tenant (or one named by ``X-Tenant-Id`` for
    local multi-tenant testing), so every query still goes through a
    tenant_id filter rather than skipping isolation "temporarily".
    """
    name = x_tenant_id or _DEFAULT_TENANT_NAME
    tenant = db.query(Tenant).filter(Tenant.name == name).first()
    if tenant is None:
        tenant = Tenant(name=name)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return tenant.id
