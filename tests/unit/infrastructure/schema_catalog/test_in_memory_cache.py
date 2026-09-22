"""Fase 2 — InMemorySchemaCache. Ver .cursor/specs/fase2.spec.md, secao 3.1."""

from datetime import datetime, timedelta, timezone

from auditor.domain.entities.entity_report import SchemaOrigin, SchemaSource
from auditor.domain.ports.schema_catalog_port import ResolvedSchema
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.infrastructure.schema_catalog.in_memory_cache import InMemorySchemaCache


class _FakeClock:
    """Relogio controlavel manualmente — evita time.sleep() real nos testes."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _resolved_schema(model_name: str = "Streetlight") -> ResolvedSchema:
    return ResolvedSchema(
        data_model=DataModelRef(
            subject="dataModel.Streetlighting",
            model_name=model_name,
            version="latest",
            schema_url="https://example.org/schema.json",
        ),
        content={"required": ["id", "type"]},
        origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=datetime.now(timezone.utc)),
    )


class TestGetSet:
    def test_freshly_inserted_schema_is_returned_immediately(self):
        cache = InMemorySchemaCache()
        schema = _resolved_schema()

        cache.set(EntityType("Streetlight"), schema)

        assert cache.get(EntityType("Streetlight")) is schema

    def test_missing_entry_returns_none(self):
        cache = InMemorySchemaCache()
        assert cache.get(EntityType("Streetlight")) is None


class TestTtlExpiration:
    def test_entry_older_than_ttl_is_treated_as_expired(self):
        clock = _FakeClock()
        cache = InMemorySchemaCache(ttl=timedelta(minutes=5), clock=clock)
        schema = _resolved_schema()

        cache.set(EntityType("Streetlight"), schema)
        clock.advance(timedelta(minutes=6))

        assert cache.get(EntityType("Streetlight")) is None

    def test_entry_within_ttl_is_still_returned(self):
        clock = _FakeClock()
        cache = InMemorySchemaCache(ttl=timedelta(minutes=5), clock=clock)
        schema = _resolved_schema()

        cache.set(EntityType("Streetlight"), schema)
        clock.advance(timedelta(minutes=4))

        assert cache.get(EntityType("Streetlight")) is schema


class TestLruEviction:
    def test_least_recently_used_entry_is_evicted_at_capacity(self):
        clock = _FakeClock()
        cache = InMemorySchemaCache(max_size=2, clock=clock)

        cache.set(EntityType("A"), _resolved_schema("A"))
        cache.set(EntityType("B"), _resolved_schema("B"))
        cache.set(EntityType("C"), _resolved_schema("C"))  # deve expulsar "A"

        assert cache.get(EntityType("A")) is None
        assert cache.get(EntityType("B")) is not None
        assert cache.get(EntityType("C")) is not None

    def test_accessing_an_entry_protects_it_from_eviction(self):
        clock = _FakeClock()
        cache = InMemorySchemaCache(max_size=2, clock=clock)

        cache.set(EntityType("A"), _resolved_schema("A"))
        cache.set(EntityType("B"), _resolved_schema("B"))
        cache.get(EntityType("A"))  # marca "A" como usado recentemente
        cache.set(EntityType("C"), _resolved_schema("C"))  # deve expulsar "B", nao "A"

        assert cache.get(EntityType("A")) is not None
        assert cache.get(EntityType("B")) is None
