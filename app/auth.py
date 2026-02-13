import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk
from jose.utils import base64url_decode


CLERK_JWT_ISSUER_URL = os.getenv("CLERK_JWT_ISSUER_URL")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL")

if not CLERK_JWKS_URL:
    # Fail fast in environments where auth should be configured.
    # In local dev you can set dummy values until Clerk is wired.
    pass


security = HTTPBearer(auto_error=False)

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_fetched_at: Optional[float] = None
_JWKS_TTL_SECONDS = 300.0


@dataclass
class CurrentUser:
    """Lightweight representation of the authenticated user."""

    user_id: str
    org_id: str
    email: Optional[str] = None
    role: Optional[str] = None


async def _get_jwks() -> Dict[str, Any]:
    """Fetch and cache Clerk JWKS."""
    global _jwks_cache, _jwks_fetched_at

    if _jwks_cache and _jwks_fetched_at:
        if time.time() - _jwks_fetched_at < _JWKS_TTL_SECONDS:
            return _jwks_cache

    if not CLERK_JWKS_URL:
        raise RuntimeError("CLERK_JWKS_URL is not configured")

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(CLERK_JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = time.time()
        return _jwks_cache


def _get_token_from_header(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return credentials.credentials


def _select_jwk(token: str, jwks: Dict[str, Any]) -> Dict[str, Any]:
    try:
        headers = jwt.get_unverified_header(token)
    except Exception:
        # Malformed / non-JWT token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
        )

    kid = headers.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
        )

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No matching JWK for token",
    )


def _verify_signature(token: str, key_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify JWT signature using the JWK and return claims.

    We do explicit signature verification so we don't accidentally skip checks.
    """
    try:
        public_key = jwk.construct(key_dict, algorithm=key_dict.get("alg"))
        message, encoded_sig = token.rsplit(".", 1)
        decoded_sig = base64url_decode(encoded_sig.encode())

        if not public_key.verify(message.encode(), decoded_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature",
            )

        claims = jwt.get_unverified_claims(token)

        if CLERK_JWT_ISSUER_URL and claims.get("iss") != CLERK_JWT_ISSUER_URL:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
            )

        # Basic expiry check
        exp = claims.get("exp")
        if exp is not None and time.time() > float(exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )

        return claims
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """
    FastAPI dependency that verifies a Clerk JWT and returns the current user.

    - Expects `Authorization: Bearer <JWT>` header.
    - Verifies JWT using Clerk JWKS and issuer.
    - Extracts `org_id` from JWT claims.
    - Raises 401 on any validation error.
    """
    token = _get_token_from_header(credentials)
    jwks = await _get_jwks()
    key_dict = _select_jwk(token, jwks)
    claims = _verify_signature(token, key_dict)

    org_id = claims.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing org_id in token",
        )

    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user identifier in token",
        )

    email = claims.get("email")
    role = claims.get("role")

    return CurrentUser(user_id=user_id, org_id=str(org_id), email=email, role=role)


