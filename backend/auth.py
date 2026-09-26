"""Authentication: bank API keys and customer session tokens.

NarrAI never handles customer passwords. The bank authenticates its customer in its
own app, then its backend (holding a NarrAI API key for that bank) asks NarrAI for a
short-lived session token for that customer. The token names the bank and customer,
so every request is tied to exactly one of each.

- API keys: random, shown once, stored only as a SHA-256 hash (they are high-entropy,
  so a slow password hash isn't needed); the prefix identifies a key in logs and lists.
- Session tokens: HS256-signed JWTs with bank, customer, expiry and a unique id.
"""

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

logger = logging.getLogger(__name__)

ISSUER = "narrai"
ALGORITHM = "HS256"
API_KEY_PREFIX = "nk_"
DEV_SECRET_FILE = Path(__file__).parent / "data" / ".token-secret"


class InvalidToken(Exception):
    pass


def session_minutes() -> int:
    return int(os.getenv("NARRAI_SESSION_MINUTES", "30"))


def _secret() -> str:
    secret = os.getenv("NARRAI_TOKEN_SECRET")
    if secret:
        if len(secret) < 32:
            raise RuntimeError("NARRAI_TOKEN_SECRET must be at least 32 characters")
        return secret
    # Development only: a random secret kept on disk so sessions survive auto-reloads.
    if not DEV_SECRET_FILE.exists():
        DEV_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEV_SECRET_FILE.write_text(secrets.token_urlsafe(48))
        DEV_SECRET_FILE.chmod(0o600)
        logger.warning("NARRAI_TOKEN_SECRET is not set; using a development secret in %s", DEV_SECRET_FILE)
    return DEV_SECRET_FILE.read_text().strip()


def issue_session(tenant_id: str, customer_id: str, generation: int = 0) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=session_minutes())
    claims = {
        "iss": ISSUER,
        "sub": customer_id,
        "tenant": tenant_id,
        "iat": now,
        "exp": expires,
        "jti": uuid.uuid4().hex,
        "gen": generation,  # must match the customer's current session generation
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM), expires


def verify_session(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],  # never accept "none" or another algorithm
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if not isinstance(claims.get("tenant"), str):
        raise InvalidToken("token has no bank")
    return claims


def new_api_key() -> tuple[str, str, str]:
    """Returns (full key to show once, prefix for identification, hash to store)."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:12], hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
