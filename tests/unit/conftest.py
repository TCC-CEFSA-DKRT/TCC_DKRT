import pytest

from auditor.infrastructure.config.settings import Settings


@pytest.fixture(autouse=True)
def _no_dotenv_in_unit_tests(monkeypatch):
    # Unit tests must be isolated from a local .env (real DB creds, broker
    # keys, etc.) -- Settings() reads it directly via pydantic-settings,
    # which monkeypatch.delenv on os.environ cannot override.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
