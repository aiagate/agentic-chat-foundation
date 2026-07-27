"""Short-lived provider continuation state for one AI generation run."""

from pydantic import BaseModel, ConfigDict, Field


class AIContinuation(BaseModel):
    """Opaque provider state passed back only during the current generation run."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(description="Provider that owns the opaque state.")
    payload: str = Field(description="Provider-owned serialized continuation state.")
