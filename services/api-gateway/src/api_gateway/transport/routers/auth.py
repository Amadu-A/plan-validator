# services/api-gateway/src/api_gateway/transport/routers/auth.py

"""Public authentication facade API Gateway."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)
from plan_validator_common.exceptions import (
    AuthenticationError,
)

from api_gateway.core.container import (
    GatewayContainer,
)
from api_gateway.transport.auth_schemas import (
    AuthUserResponse,
    LoginRequest,
    RegisterRequest,
)
from api_gateway.transport.dependencies import (
    get_container,
)
from api_gateway.transport.session_cookie import (
    delete_session_cookie,
    read_session_cookie,
    set_session_cookie,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

ContainerDependency = Annotated[
    GatewayContainer,
    Depends(get_container),
]


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    response: Response,
    container: ContainerDependency,
) -> AuthUserResponse:
    """Регистрирует user через Auth Service и устанавливает HttpOnly cookie."""
    result = await container.auth_service.register_user(
        email=str(request.email),
        password=(request.password.get_secret_value()),
    )

    set_session_cookie(
        response=response,
        settings=(container.settings.session_cookie),
        session_token=(result.session_token),
    )

    return AuthUserResponse.from_dto(result.user)


@router.post(
    "/login",
    response_model=AuthUserResponse,
)
async def login(
    request: LoginRequest,
    response: Response,
    container: ContainerDependency,
) -> AuthUserResponse:
    """Создаёт opaque session и не возвращает raw token в JSON."""
    result = await container.auth_service.login_user(
        email=str(request.email),
        password=(request.password.get_secret_value()),
    )

    set_session_cookie(
        response=response,
        settings=(container.settings.session_cookie),
        session_token=(result.session_token),
    )

    return AuthUserResponse.from_dto(result.user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Идемпотентно отзывает session и очищает browser cookie."""
    cookie_settings = container.settings.session_cookie

    session_token = read_session_cookie(
        request=request,
        settings=cookie_settings,
    )

    if session_token is not None:
        await container.auth_service.logout_session(session_token=session_token)

    response = Response(status_code=(status.HTTP_204_NO_CONTENT))

    delete_session_cookie(
        response=response,
        settings=cookie_settings,
    )

    return response


@router.get(
    "/me",
    response_model=AuthUserResponse,
)
async def current_user(
    request: Request,
    container: ContainerDependency,
) -> AuthUserResponse:
    """Возвращает current user по HttpOnly session cookie."""
    session_token = read_session_cookie(
        request=request,
        settings=(container.settings.session_cookie),
    )

    if session_token is None:
        raise AuthenticationError("Authentication required")

    user = await container.auth_service.get_current_user(session_token=session_token)

    return AuthUserResponse.from_dto(user)
