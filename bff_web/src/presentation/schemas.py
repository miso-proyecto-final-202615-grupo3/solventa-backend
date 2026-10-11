from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PasswordVerify(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ClienteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    tipo_documento: str = Field(pattern="^CC$")
    numero_identificacion: str = Field(min_length=5, max_length=30)
    correo: EmailStr
    password: str = Field(min_length=8, max_length=128)
    fecha_nacimiento: date
    pais_residencia: str = Field(min_length=2, max_length=60)
    telefono: str = Field(min_length=7, max_length=20)