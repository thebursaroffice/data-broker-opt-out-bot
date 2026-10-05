"""Authenticated encryption for anything personal we write to disk.

Every blob carries its own random nonce. The associated data ties a blob to
its purpose, so a wrapped key can't be swapped in where a profile is
expected (or vice versa) without decryption failing.
"""

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

KEY_BYTES = 32
NONCE_BYTES = 12
SALT_BYTES = 16


class DecryptionError(Exception):
    """Wrong key, or the data was modified. AES-GCM can't tell which."""


@dataclass(frozen=True)
class ScryptParams:
    # ~128 MiB and a fraction of a second on a laptop: tolerable once per
    # command, expensive for anyone brute-forcing a stolen database.
    n: int = 2**17
    r: int = 8
    p: int = 1


def new_key() -> bytes:
    return AESGCM.generate_key(bit_length=KEY_BYTES * 8)


def new_salt() -> bytes:
    return os.urandom(SALT_BYTES)


def encrypt(key: bytes, plaintext: bytes, purpose: str) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, _aad(purpose))


def decrypt(key: bytes, blob: bytes, purpose: str) -> bytes:
    if len(blob) <= NONCE_BYTES:
        raise DecryptionError("ciphertext is truncated")
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _aad(purpose))
    except InvalidTag:
        raise DecryptionError("wrong key or corrupted data") from None


def derive_key(passphrase: str, salt: bytes, params: ScryptParams) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=params.n, r=params.r, p=params.p)
    return kdf.derive(passphrase.encode("utf-8"))


def _aad(purpose: str) -> bytes:
    return f"unlisted:{purpose}".encode()
