from enum import Enum


class TipoDocumento(str, Enum):
    CC = "CC"


class EstadoKYC(str, Enum):
    PENDIENTE = "PENDIENTE"
    EN_VALIDACION = "EN_VALIDACION"
    VALIDADO = "VALIDADO"
    RECHAZADO = "RECHAZADO"
