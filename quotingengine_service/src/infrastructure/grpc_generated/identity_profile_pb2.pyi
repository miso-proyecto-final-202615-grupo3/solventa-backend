from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ObtenerPerfilClienteRequest(_message.Message):
    __slots__ = ("cliente_id",)
    CLIENTE_ID_FIELD_NUMBER: _ClassVar[int]
    cliente_id: str
    def __init__(self, cliente_id: _Optional[str] = ...) -> None: ...

class PerfilClienteResponse(_message.Message):
    __slots__ = ("id", "nombres", "apellidos", "tipo_documento", "numero_identificacion", "correo", "fecha_nacimiento", "pais_residencia", "telefono", "estado_kyc")
    ID_FIELD_NUMBER: _ClassVar[int]
    NOMBRES_FIELD_NUMBER: _ClassVar[int]
    APELLIDOS_FIELD_NUMBER: _ClassVar[int]
    TIPO_DOCUMENTO_FIELD_NUMBER: _ClassVar[int]
    NUMERO_IDENTIFICACION_FIELD_NUMBER: _ClassVar[int]
    CORREO_FIELD_NUMBER: _ClassVar[int]
    FECHA_NACIMIENTO_FIELD_NUMBER: _ClassVar[int]
    PAIS_RESIDENCIA_FIELD_NUMBER: _ClassVar[int]
    TELEFONO_FIELD_NUMBER: _ClassVar[int]
    ESTADO_KYC_FIELD_NUMBER: _ClassVar[int]
    id: str
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_identificacion: str
    correo: str
    fecha_nacimiento: str
    pais_residencia: str
    telefono: str
    estado_kyc: str
    def __init__(self, id: _Optional[str] = ..., nombres: _Optional[str] = ..., apellidos: _Optional[str] = ..., tipo_documento: _Optional[str] = ..., numero_identificacion: _Optional[str] = ..., correo: _Optional[str] = ..., fecha_nacimiento: _Optional[str] = ..., pais_residencia: _Optional[str] = ..., telefono: _Optional[str] = ..., estado_kyc: _Optional[str] = ...) -> None: ...
