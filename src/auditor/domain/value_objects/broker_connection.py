from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrokerConnectionStatus(str, Enum):
    OK = "ok"
    INVALID_URL = "invalid_url"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    UNEXPECTED_RESPONSE = "unexpected_response"


@dataclass(frozen=True)
class BrokerConnectionCheck:
    status: BrokerConnectionStatus
    entity_types_count: int | None = None
    http_status: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is BrokerConnectionStatus.OK
