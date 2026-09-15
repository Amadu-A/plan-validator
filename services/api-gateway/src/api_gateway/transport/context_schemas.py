# services/api-gateway/src/api_gateway/transport/context_schemas.py

"""Public Project Context schemas API Gateway."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api_gateway.application.context_service import (
    ContextSourceKind,
    ContextSourceState,
    GatewayContextSource,
    GatewayProjectContext,
    ProjectContextState,
)


class RegisterProjectContextSourceRequest(BaseModel):
    """Public metadata request T/PZ без client-controlled user_id."""

    model_config = ConfigDict(extra="forbid")

    kind: ContextSourceKind

    original_name: str = Field(
        min_length=1,
        max_length=512,
    )

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectContextResponse(BaseModel):
    """Public lifecycle representation Project Context."""

    id: UUID
    state: ProjectContextState

    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @classmethod
    def from_dto(
        cls,
        context: GatewayProjectContext,
    ) -> "ProjectContextResponse":
        """Скрывает internal owner field из public response."""
        return cls(
            id=context.id,
            state=context.state,
            created_at=context.created_at,
            updated_at=context.updated_at,
            expires_at=context.expires_at,
        )


class ProjectContextSourceResponse(BaseModel):
    """Public metadata representation temporary T/PZ source."""

    id: UUID
    context_id: UUID

    kind: ContextSourceKind
    original_name: str
    source_sha256: str

    state: ContextSourceState
    active_fingerprint: str | None
    chunk_count: int

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(
        cls,
        source: GatewayContextSource,
    ) -> "ProjectContextSourceResponse":
        """Скрывает internal owner field из public response."""
        return cls(
            id=source.id,
            context_id=source.context_id,
            kind=source.kind,
            original_name=source.original_name,
            source_sha256=source.source_sha256,
            state=source.state,
            active_fingerprint=source.active_fingerprint,
            chunk_count=source.chunk_count,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
