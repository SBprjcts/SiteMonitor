from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import Platform, StoreStatus
from app.stores.domain import normalize_domain


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str
    platform: Platform
    enabled: bool
    status: StoreStatus
    hot_interval_s: int
    sweep_interval_s: int
    last_ok_at: datetime | None
    consecutive_errors: int


class StoreUpdate(BaseModel):
    enabled: bool


class StoreCreate(BaseModel):
    domain: str
    name: str | None = Field(default=None, max_length=100)

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("name")
    @classmethod
    def _blank_name_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None
