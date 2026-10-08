from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# argon2 hashes any length, but an enormous password would tie up the server.
MAX_PASSWORD_LENGTH = 128


class _Credentials(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        # Stored lowercase, so "Saif@x.com" and "saif@x.com" are the same account.
        return value.strip().lower()


class RegisterRequest(_Credentials):
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(_Credentials):
    # No minimum here: a too-short password is just a wrong password.
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
