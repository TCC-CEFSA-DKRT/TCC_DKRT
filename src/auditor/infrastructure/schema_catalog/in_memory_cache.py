"""InMemorySchemaCache — cache LRU com TTL para ResolvedSchema. Ver
.cursor/specs/fase2.spec.md, secao 3.1.

`clock` e injetavel de proposito: os testes de expiracao de TTL nao devem
depender de `time.sleep()` real.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Callable

from auditor.domain.ports.schema_catalog_port import ResolvedSchema
from auditor.domain.value_objects.entity_type import EntityType

_DEFAULT_TTL = timedelta(minutes=5)
_DEFAULT_MAX_SIZE = 256


class InMemorySchemaCache:
    def __init__(
        self,
        ttl: timedelta = _DEFAULT_TTL,
        max_size: int = _DEFAULT_MAX_SIZE,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._store: "OrderedDict[str, tuple[ResolvedSchema, datetime]]" = OrderedDict()

    def get(self, entity_type: EntityType) -> ResolvedSchema | None:
        key = entity_type.value
        entry = self._store.get(key)
        if entry is None:
            return None
        schema, inserted_at = entry
        if self._clock() - inserted_at > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return schema

    def set(self, entity_type: EntityType, schema: ResolvedSchema) -> None:
        key = entity_type.value
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self._max_size:
            self._store.popitem(last=False)  # remove o menos recentemente usado (LRU)
        self._store[key] = (schema, self._clock())
