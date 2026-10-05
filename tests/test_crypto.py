import pytest

from unlisted import crypto

PARAMS = crypto.ScryptParams(n=2**10, r=8, p=1)


def test_roundtrip() -> None:
    key = crypto.new_key()
    blob = crypto.encrypt(key, b"fake secret", "test")
    assert crypto.decrypt(key, blob, "test") == b"fake secret"


def test_nonce_is_fresh_each_time() -> None:
    key = crypto.new_key()
    assert crypto.encrypt(key, b"same", "test") != crypto.encrypt(key, b"same", "test")


def test_wrong_key_rejected() -> None:
    blob = crypto.encrypt(crypto.new_key(), b"fake secret", "test")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(crypto.new_key(), blob, "test")


def test_tampering_detected() -> None:
    key = crypto.new_key()
    blob = bytearray(crypto.encrypt(key, b"fake secret", "test"))
    blob[-1] ^= 0x01
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(key, bytes(blob), "test")


def test_blob_bound_to_purpose() -> None:
    key = crypto.new_key()
    blob = crypto.encrypt(key, b"fake secret", "profile")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(key, blob, "wrapped-key")


def test_truncated_blob_rejected() -> None:
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(crypto.new_key(), b"short", "test")


def test_derived_key_depends_on_passphrase_and_salt() -> None:
    salt = crypto.new_salt()
    a = crypto.derive_key("correct horse", salt, PARAMS)
    assert a == crypto.derive_key("correct horse", salt, PARAMS)
    assert a != crypto.derive_key("wrong horse", salt, PARAMS)
    assert a != crypto.derive_key("correct horse", crypto.new_salt(), PARAMS)
    assert len(a) == crypto.KEY_BYTES
