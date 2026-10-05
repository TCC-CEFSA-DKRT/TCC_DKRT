from __future__ import annotations

from pathlib import Path

import pytest

from auditor.interfaces.aws_lambda import admin_handler
from auditor.interfaces.cli import main as cli_main

DOCKERFILE = Path(__file__).resolve().parents[4] / "Dockerfile"


class _FakeTenantAccountRepository:
    def __init__(self, count: int = 0):
        self._count = count
        self.create_calls: list[dict] = []

    async def rotate_encryption(self) -> int:
        return self._count

    async def create(self, tenant, broker_url, broker_api_key=None, login_email=None, password=None):
        self.create_calls.append({"login_email": login_email, "password": password})


class _UpgradeRecorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, cfg, revision):
        self.calls.append((cfg, revision))


class TestRotateKeys:
    def test_rotate_keys_returns_exit_code_zero_and_the_row_count(self, monkeypatch):
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: _FakeTenantAccountRepository(3))

        result = admin_handler.handler({"argv": ["tenant", "rotate-keys"]}, None)

        assert result["exit_code"] == 0
        assert "Chaves rotacionadas: 3" in result["output"]


class TestRegisterNeverLeaksThePasswordToCloudWatch:
    def test_generated_password_comes_back_only_in_the_response(self, monkeypatch, capsys):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        result = admin_handler.handler(
            {
                "argv": [
                    "tenant",
                    "register",
                    "--tenant",
                    "acme",
                    "--broker-url",
                    "https://orion.acme.com",
                    "--email",
                    "ops@acme.com",
                ]
            },
            None,
        )

        assert "Senha inicial" in result["output"]
        assert "Senha inicial" not in capsys.readouterr().out


class TestUsageErrorsAreExitCodeTwoWithoutRaising:
    def test_missing_required_option_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: _FakeTenantAccountRepository())

        result = admin_handler.handler({"argv": ["tenant", "register"]}, None)

        assert result["exit_code"] == 2


class TestMigrate:
    def test_migrate_upgrades_head_with_the_repo_migrations_directory(self, monkeypatch):
        recorder = _UpgradeRecorder()
        monkeypatch.setattr(admin_handler.command, "upgrade", recorder)

        result = admin_handler.handler({"argv": ["migrate"]}, None)

        assert result["exit_code"] == 0
        assert len(recorder.calls) == 1
        cfg, revision = recorder.calls[0]
        assert revision == "head"
        assert cfg.get_main_option("script_location").endswith("migrations")


class TestDockerfileCopiesAlembicAssets:
    def test_dockerfile_copies_alembic_ini_and_migrations(self):
        content = DOCKERFILE.read_text()

        assert "COPY alembic.ini" in content
        assert "COPY migrations" in content
