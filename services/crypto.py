"""Secret encryption for endpoint API keys and (later) mail credentials.

Part 1.6: "No plaintext." Keys are encrypted at rest with Fernet (AES-128-CBC
+ HMAC). The Fernet key is derived from a passphrase in the ATELIER_SECRET env
var when set; otherwise a random key is generated once and stored in
data/.fernet.key (and that file is gitignored along with the rest of data/).

Deriving from a passphrase is the preferred path because the encrypted blobs
are then portable across machines that share the passphrase. The generated-key
fallback keeps a fresh install working with zero configuration.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_DATA_DIR = Path("data")
_KEY_FILE = _DATA_DIR / ".fernet.key"
# Fixed salt: the passphrase is the secret, and a stable salt keeps blobs
# decryptable across restarts. (A per-install random salt would also work but
# would have to be persisted anyway, so it buys nothing here.)
_SALT = b"the-atelier-v1-secret-salt"

_fernet: Fernet | None = None


def _derive_from_passphrase(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=200_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _load_or_create_key() -> bytes:
    passphrase = os.getenv("ATELIER_SECRET")
    if passphrase:
        return _derive_from_passphrase(passphrase)
    _DATA_DIR.mkdir(exist_ok=True)
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass  # best-effort on Windows
    return key


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _f().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _f().decrypt(token.encode()).decode()
    except InvalidToken:
        # Most likely a value stored before encryption existed, or a changed
        # passphrase. Return as-is so the app degrades rather than crashing.
        return token
