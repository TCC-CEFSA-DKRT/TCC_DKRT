from __future__ import annotations

import asyncio
import secrets
from functools import cache

from fastapi import APIRouter, Depends, HTTPException, status

from auditor.infrastructure.config.container import get_settings, get_tenant_account_repository
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccountRepository,
    hash_password,
    verify_password,
)
from auditor.interfaces.rest.access_tokens import issue_access_token
from auditor.interfaces.rest.schemas import AccessTokenResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@cache
def _dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def _password_matches(password: str, password_hash: str | None) -> bool:
    return verify_password(password, password_hash or _dummy_password_hash())


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    repository: TenantAccountRepository = Depends(get_tenant_account_repository),
) -> AccessTokenResponse:
    account = await repository.get_by_login_email(body.login_email)
    password_ok = await asyncio.to_thread(
        _password_matches, body.password, account.password_hash if account else None
    )
    if account is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha invalidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AccessTokenResponse(access_token=issue_access_token(account.tenant, settings))
