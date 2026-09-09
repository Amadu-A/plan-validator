# services/api-gateway/src/api_gateway/transport/session_cookie.py

"""HttpOnly cookie helpers opaque authentication session."""

from fastapi import (
    Request,
    Response,
)

from api_gateway.core.settings import (
    SessionCookieSettings,
)


def read_session_cookie(
    *,
    request: Request,
    settings: SessionCookieSettings,
) -> str | None:
    """Читает raw opaque token только из configured HttpOnly cookie."""
    return request.cookies.get(settings.name)


def set_session_cookie(
    *,
    response: Response,
    settings: SessionCookieSettings,
    session_token: str,
) -> None:
    """Устанавливает opaque token с безопасными cookie attributes."""
    response.set_cookie(
        key=settings.name,
        value=session_token,
        max_age=(settings.max_age_seconds),
        httponly=True,
        secure=settings.secure,
        samesite=settings.same_site,
        path=settings.path,
    )


def delete_session_cookie(
    *,
    response: Response,
    settings: SessionCookieSettings,
) -> None:
    """Удаляет browser session cookie с теми же scope attributes."""
    response.delete_cookie(
        key=settings.name,
        path=settings.path,
        secure=settings.secure,
        httponly=True,
        samesite=settings.same_site,
    )
