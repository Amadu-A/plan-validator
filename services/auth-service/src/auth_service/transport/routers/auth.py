# services/auth-service/src/auth_service/transport/routers/auth.py

"""Internal authentication router Authentication Service."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)

from auth_service.core.container import (
    AuthContainer,
)
from auth_service.transport.dependencies import (
    get_container,
)
from auth_service.transport.schemas import (
    AuthSessionResponse,
    LoginRequest,
    RegisterRequest,
    SessionTokenRequest,
    UserResponse,
)

router = APIRouter(
    prefix="/auth",
    tags=["internal-auth"],
)

ContainerDependency = Annotated[
    AuthContainer,
    Depends(get_container),
]


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    container: ContainerDependency,
) -> AuthSessionResponse:
    """Регистрирует user и возвращает token только trusted Gateway."""
    result = await container.register_user.execute(
        email=str(request.email),
        password=(request.password.get_secret_value()),
    )

    return AuthSessionResponse.from_dto(result)


@router.post(
    "/login",
    response_model=AuthSessionResponse,
)
async def login(
    request: LoginRequest,
    container: ContainerDependency,
) -> AuthSessionResponse:
    """Проверяет credentials и создаёт independent session."""
    result = await container.login_user.execute(
        email=str(request.email),
        password=(request.password.get_secret_value()),
    )

    return AuthSessionResponse.from_dto(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: SessionTokenRequest,
    container: ContainerDependency,
) -> Response:
    """Идемпотентно отзывает opaque session."""
    await container.logout_user.execute(session_token=(request.session_token.get_secret_value()))

    return Response(status_code=(status.HTTP_204_NO_CONTENT))


@router.post(
    "/session",
    response_model=UserResponse,
)
async def resolve_session(
    request: SessionTokenRequest,
    container: ContainerDependency,
) -> UserResponse:
    """Разрешает raw token в safe authenticated user."""
    user = await container.get_current_user.execute(
        session_token=(request.session_token.get_secret_value())
    )

    return UserResponse.from_dto(user)
