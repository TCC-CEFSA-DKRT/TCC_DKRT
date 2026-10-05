import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: testes que exigem Orion")
