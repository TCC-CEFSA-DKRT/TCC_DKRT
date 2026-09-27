from __future__ import annotations

import pytest

from auditor.infrastructure.persistence.tenant_account_repository import (
    hash_password,
    verify_password,
)


class TestHashPassword:
    def test_hash_password_never_returns_the_plaintext_and_is_bcrypt(self):
        password_hash = hash_password("senha-super-secreta")

        assert password_hash != "senha-super-secreta"
        assert password_hash.startswith("$2b$")

    def test_hash_password_rejects_more_than_72_utf8_bytes(self):
        too_long = "ã" * 37
        fits_exactly = "ã" * 36

        with pytest.raises(ValueError):
            hash_password(too_long)

        hash_password(fits_exactly)


class TestVerifyPassword:
    def test_verify_password_rejects_more_than_72_utf8_bytes_without_raising(self):
        assert verify_password("ã" * 37, hash_password("x")) is False

    def test_verify_password_accepts_the_correct_password(self):
        password = "senha-super-secreta"

        assert verify_password(password, hash_password(password)) is True

    def test_verify_password_rejects_a_wrong_password(self):
        password_hash = hash_password("senha-super-secreta")

        assert verify_password("senha-errada", password_hash) is False
