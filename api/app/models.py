from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
RuleKind = Literal["banned_word", "term", "tone", "claim_policy", "accessibility"]


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    voice_guide: str = Field(default="", max_length=20000)
    colors: list[str] = Field(default_factory=list, max_length=20)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    voice_guide: str | None = Field(default=None, max_length=20000)
    colors: list[str] | None = Field(default=None, max_length=20)


class FactIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="", max_length=500)


class RuleIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    kind: RuleKind
    pattern: str = Field(min_length=1, max_length=300)
    replacement: str | None = Field(default=None, max_length=300)
    message: str = Field(min_length=1, max_length=500)
    severity: Severity = "medium"


class ScanIn(BaseModel):
    brand_id: UUID
    content: str = Field(min_length=1, max_length=20000)
    channel: str = Field(default="social", max_length=40)
    author: str = Field(default="creator", max_length=80)


class ContentIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    author: str = Field(default="creator", max_length=80)


class DecisionIn(BaseModel):
    decision: Literal["accepted", "edited", "ignored", "open"]
    reason: str | None = Field(default=None, max_length=500)
    edited_text: str | None = Field(default=None, max_length=2000)
    author: str = Field(default="creator", max_length=80)


class ReviewIn(BaseModel):
    action: Literal["approve", "send_back"]
    comment: str = Field(default="", max_length=1000)
    reviewer: str = Field(default="manager", max_length=80)
