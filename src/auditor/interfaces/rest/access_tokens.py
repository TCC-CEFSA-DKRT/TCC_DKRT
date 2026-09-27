from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.settings import Settings

JWT_ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "auditor_session"
_REQUIRED_CLAIMS = ["exp", "fiware_service", "fiware_service_path"]


def _signing_key(settings: Settings) -> str:
    if settings.jwt_signing_key is None:
        raise RuntimeError("JWT_SIGNING_KEY nao configurada")
    return settings.jwt_signing_key.get_secret_value()


def issue_access_token(tenant: Tenant, settings: Settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    return jwt.encode(
        {
            "fiware_service": tenant.fiware_service,
            "fiware_service_path": tenant.fiware_service_path,
            "exp": expires_at,
        },
        _signing_key(settings),
        algorithm=JWT_ALGORITHM,
    )


def tenant_from_access_token(token: str, settings: Settings) -> Tenant:
    claims = jwt.decode(
        token,
        _signing_key(settings),
        algorithms=[JWT_ALGORITHM],
        options={"require": _REQUIRED_CLAIMS},
    )
    service, path = claims["fiware_service"], claims["fiware_service_path"]
    if not isinstance(service, str) or not isinstance(path, str):
        raise jwt.InvalidTokenError("claims de tenant com tipo invalido")
    return Tenant(fiware_service=service, fiware_service_path=path)
