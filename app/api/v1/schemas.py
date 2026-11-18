"""Request and response bodies shared by the /api/v1 routes of phase C1."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.access import Role, TokenScope
from app.repos.users import MAX_EMAIL_LENGTH, normalise_email
from app.security.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

Email = Annotated[
    str, Field(max_length=MAX_EMAIL_LENGTH + 64), AfterValidator(normalise_email)
]
NewPassword = Annotated[
    str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]
# Sign-in checks any length up to the maximum; the minimum applies to new ones.
AnyPassword = Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class Body(BaseModel):
    """A request body: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class Credentials(Body):
    email: Email
    password: AnyPassword


class NewAccount(Body):
    email: Email
    password: NewPassword


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role
    disabled: bool
    locked_until: datetime | None
    created_at: datetime


class SignedIn(BaseModel):
    user: UserOut
    csrf_token: str


class Me(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    csrf_token: str


class SetupState(BaseModel):
    needs_first_run: bool


class NewUser(Body):
    email: Email
    password: NewPassword
    role: Role


class UserPatch(Body):
    """Only the fields sent change. A new password also clears a lockout."""

    role: Role | None = None
    disabled: bool | None = None
    password: NewPassword | None = None


class UserPage(BaseModel):
    items: list[UserOut]
    next_cursor: str | None


class NewToken(Body):
    label: Label
    scope: TokenScope


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    scope: TokenScope
    created_by: uuid.UUID | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class CreatedToken(TokenOut):
    """The new token with its value. The value is shown this once only."""

    token: str


class TokenPage(BaseModel):
    items: list[TokenOut]
    next_cursor: str | None
