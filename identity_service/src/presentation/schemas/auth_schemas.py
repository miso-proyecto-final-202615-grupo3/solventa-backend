from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PasswordVerify(BaseModel):
    """Credenciales para autenticar a un cliente."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)
