from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    email: str
    password: str
    otp: str = ""


class GoogleAuthPayload(BaseModel):
    credential: str


class RegisterPayload(BaseModel):
    name: str = Field(default="Designer", max_length=80)
    email: str
    password: str


class PasswordResetRequestPayload(BaseModel):
    email: str


class PasswordResetConfirmPayload(BaseModel):
    token: str
    newPassword: str


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    username: str | None = Field(default=None, max_length=80)
    settings: dict[str, Any] | None = None


class PasswordPatch(BaseModel):
    currentPassword: str
    newPassword: str


class TwoFactorVerifyPayload(BaseModel):
    code: str


class UploadFromUrlPayload(BaseModel):
    url: str


class GenerationJobCreatePayload(BaseModel):
    uploadId: str
    roomType: str = "living_room"
    style: str = "modern"
    requirements: dict[str, Any] = Field(default_factory=dict)
    prompt: str = ""
    negativePrompt: str = ""
    provider: str = ""
    model: str = ""
    variantCount: int = Field(default=4, ge=1, le=4)
    settings: dict[str, Any] = Field(default_factory=dict)
    seeds: list[int] = Field(default_factory=list)


class ShareCreatePayload(BaseModel):
    expiresHours: int = Field(default=72, ge=1, le=24 * 30)
    password: str = Field(default="", max_length=128)


class ShareUnlockPayload(BaseModel):
    password: str = ""


JobState = Literal["queued", "running", "completed", "failed", "cancelled"]
