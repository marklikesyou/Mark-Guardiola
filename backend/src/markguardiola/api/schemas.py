from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str = "markguardiola-api"
    version: str
    timestamp: datetime


class ReadyDependency(ApiModel):
    name: str
    ready: bool
    detail: str | None = None


class ReadyResponse(ApiModel):
    status: Literal["ready", "not_ready"]
    dependencies: list[ReadyDependency]
    timestamp: datetime
