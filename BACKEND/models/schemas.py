from __future__ import annotations

from typing import Any, Annotated

from pydantic import BaseModel, EmailStr, Field


class LoginPayload(BaseModel):
    email: EmailStr
    password: str
    otp: str = ""


class RegisterPayload(BaseModel):
    name: str = Field(default="Designer", max_length=80)
    email: EmailStr
    password: str


class PasswordResetRequestPayload(BaseModel):
    email: EmailStr


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


class GenerationJobCreatePayload(BaseModel):
    uploadId: str
    roomType: str = "living_room"
    style: str = "modern"
    requirements: dict[str, Any] = Field(default_factory=dict)
    prompt: str = ""
    negativePrompt: str = ""
    provider: str = ""
    model: str = ""
    variantCount: Annotated[int, Field(ge=1, le=4)] = 4
    settings: dict[str, Any] = Field(default_factory=dict)
    seeds: list[int] = Field(default_factory=list)


class ShareCreatePayload(BaseModel):
    expiresHours: Annotated[int, Field(ge=1, le=720)] = 72
    password: str = Field(default="", max_length=128)


class ShareUnlockPayload(BaseModel):
    password: str = ""

