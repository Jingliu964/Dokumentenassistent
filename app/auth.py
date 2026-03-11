from dataclasses import dataclass

from fastapi import Header, HTTPException

from .settings import AUTH_REQUIRED, API_KEY_INFO, DEFAULT_TENANT


ROLE_ORDER = {"reader": 1, "editor": 2, "admin": 3}


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    role: str
    user_id: str | None
    api_key: str | None


def require_tenant(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_user: str | None = Header(default=None, alias="X-User"),
) -> TenantContext:
    if not AUTH_REQUIRED:
        return TenantContext(tenant_id=DEFAULT_TENANT, role="admin", user_id=x_user, api_key=x_api_key)

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")

    info = API_KEY_INFO.get(x_api_key)
    if not info:
        raise HTTPException(status_code=403, detail="Invalid API key.")

    return TenantContext(tenant_id=info.tenant_id, role=info.role, user_id=x_user, api_key=x_api_key)


def require_role(ctx: TenantContext, min_role: str) -> None:
    min_value = ROLE_ORDER.get(min_role, 0)
    user_value = ROLE_ORDER.get(ctx.role, 0)
    if user_value < min_value:
        raise HTTPException(status_code=403, detail=f"Insufficient role. Requires {min_role}.")
