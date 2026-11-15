from enum import Enum


class EstadoSiniestro(str, Enum):
    """Ciclo de vida del siniestro. HU4.1.1 solo crea `REPORTADO`; el resto llega con HU4.2.x."""

    REPORTADO = "REPORTADO"
    EN_EVALUACION = "EN_EVALUACION"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PAGADO = "PAGADO"


class CanalReporte(str, Enum):
    MOVIL = "MOVIL"
    PARAMETRICO = "PARAMETRICO"
