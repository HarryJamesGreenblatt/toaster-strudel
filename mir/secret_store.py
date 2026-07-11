"""Secret access seam for toaster-strudel.

ONE indirection for every secret the pipeline needs (AcoustID, Discogs, ...).
Callers only ever do ``get_secret("ACOUSTID_CLIENT_KEY")`` and never care where
it lives. Lookup order:

    1. keyring  -> Windows Credential Manager (preferred, encrypted, no file)
    2. os.environ
    3. a gitignored .env file (repo root or mir/)

To migrate to Azure Key Vault later, edit ONLY this file (add a ``_from_keyvault``
resolver at the front of ``get_secret``); no caller changes.

Store a secret the preferred way (never commits a plaintext file)::

    python -c "import keyring; keyring.set_password('toaster-strudel','ACOUSTID_CLIENT_KEY','YOUR_KEY')"
"""
from __future__ import annotations

import os
from pathlib import Path

SERVICE = "toaster-strudel"


def _from_keyring(name: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def _from_dotenv(name: str) -> str | None:
    here = Path(__file__).resolve().parent
    for base in (here, here.parent):  # mir/ then repo root
        env = base / ".env"
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == name:
                return val.strip().strip('"').strip("'")
    return None


def get_secret(name: str, *, required: bool = True) -> str | None:
    """Resolve a secret by name. Raises if ``required`` and not found."""
    value = _from_keyring(name) or os.environ.get(name) or _from_dotenv(name)
    if not value and required:
        raise RuntimeError(
            f"Secret {name!r} not found. Store it (preferred, no plaintext file):\n"
            f"  python -c \"import keyring; keyring.set_password('{SERVICE}','{name}','YOUR_KEY')\"\n"
            f"or add a line  {name}=...  to a gitignored .env file."
        )
    return value


if __name__ == "__main__":
    import sys

    names = sys.argv[1:] or ["ACOUSTID_CLIENT_KEY", "DISCOGS_TOKEN"]
    for n in names:
        v = get_secret(n, required=False)
        print(f"{n}: {'set (' + str(len(v)) + ' chars)' if v else 'MISSING'}")
