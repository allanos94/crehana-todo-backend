"""`JwtTokenService`: the `TokenService` adapter backed by PyJWT (design
ADR-11). Tokens are HS256-signed, carry a `type` claim identifying access vs
refresh, and times come from the injected `Clock`, never `datetime.now()`,
so tests control expiry deterministically.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.application.exceptions import InvalidTokenError
from app.application.ports import Clock, TokenPair, TokenType

_ALGORITHM = "HS256"
_ACCESS_TTL = timedelta(minutes=15)
_REFRESH_TTL = timedelta(days=7)
_REQUIRED_CLAIMS = ["sub", "type", "iat", "exp"]


class JwtTokenService:
    """Issues and decodes HS256 access/refresh token pairs."""

    def __init__(self, secret_key: str, clock: Clock) -> None:
        self._secret_key = secret_key
        self._clock = clock

    def issue_pair(self, user_id: UUID) -> TokenPair:
        now = self._clock.now()
        return TokenPair(
            access_token=self._encode(user_id, TokenType.ACCESS, now, _ACCESS_TTL),
            refresh_token=self._encode(user_id, TokenType.REFRESH, now, _REFRESH_TTL),
            token_type="bearer",
            expires_in=int(_ACCESS_TTL.total_seconds()),
        )

    def decode(self, token: str, expected_type: TokenType) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[_ALGORITHM],
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError() from exc

        if payload.get("type") != expected_type.value:
            raise InvalidTokenError()
        return UUID(str(payload["sub"]))

    def _encode(
        self,
        user_id: UUID,
        token_type: TokenType,
        issued_at: datetime,
        ttl: timedelta,
    ) -> str:
        payload = {
            "sub": str(user_id),
            "type": token_type.value,
            "iat": issued_at,
            "exp": issued_at + ttl,
            "jti": uuid4().hex,
        }
        return jwt.encode(payload, self._secret_key, algorithm=_ALGORITHM)
