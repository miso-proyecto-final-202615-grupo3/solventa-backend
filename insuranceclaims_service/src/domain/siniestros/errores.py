"""Errores de dominio con el código del contrato público (`{codigo, mensaje}`)."""


class ErrorSiniestro(Exception):
    status_code = 400
    codigo = "DATOS_INVALIDOS"
    mensaje = "La solicitud no es válida."

    def __init__(self, mensaje: str | None = None) -> None:
        if mensaje:
            self.mensaje = mensaje
        super().__init__(self.codigo)


class PolizaNoEncontrada(ErrorSiniestro):
    status_code = 404
    codigo = "POLIZA_NO_ENCONTRADA"
    mensaje = "No encontramos la póliza."


class PolizaNoVigente(ErrorSiniestro):
    status_code = 409
    codigo = "POLIZA_NO_VIGENTE"
    mensaje = "La póliza no está vigente."


class FechaFueraDeVigencia(ErrorSiniestro):
    status_code = 409
    codigo = "FECHA_FUERA_DE_VIGENCIA"
    mensaje = "La fecha del evento está fuera de la vigencia de la póliza."


class FechaInvalida(ErrorSiniestro):
    status_code = 422
    codigo = "FECHA_INVALIDA"
    mensaje = "La fecha del evento no puede ser futura."


class TipoNoPermitido(ErrorSiniestro):
    status_code = 422
    codigo = "TIPO_NO_PERMITIDO"
    mensaje = "El tipo de siniestro no aplica a esta póliza."


class IdempotenciaConflicto(ErrorSiniestro):
    status_code = 409
    codigo = "IDEMPOTENCIA_CONFLICTO"
    mensaje = "La clave de idempotencia ya se usó con otros datos."


class SiniestroNoEncontrado(ErrorSiniestro):
    status_code = 404
    codigo = "SINIESTRO_NO_ENCONTRADO"
    mensaje = "No encontramos el siniestro."


class ServicioNoDisponible(ErrorSiniestro):
    status_code = 503
    codigo = "SERVICIO_NO_DISPONIBLE"
    mensaje = "El servicio no está disponible. Intenta de nuevo."
