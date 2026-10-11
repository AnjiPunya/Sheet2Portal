import re

from pydantic import BaseModel, Field, field_validator

# Deliberately simple (no extra dependency): something@something.tld.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value) or len(value) > 254:
        raise ValueError("Enter a valid email address.")
    return value


class SignUpIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=80)

    _email = field_validator("email")(_normalize_email)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if value.strip() == "" or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must be at least 8 characters and include a letter and a number.")
        return value


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _email = field_validator("email")(_normalize_email)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    permissions: list[str]
