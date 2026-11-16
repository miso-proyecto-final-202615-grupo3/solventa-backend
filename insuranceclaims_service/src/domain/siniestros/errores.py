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


# --- HU4.1.2 · Evidencias y ubicación -------------------------------------------------------------

class SiniestroNoAdmiteEvidencias(ErrorSiniestro):
    status_code = 409
    codigo = "SINIESTRO_NO_ADMITE_EVIDENCIAS"
    mensaje = "Este siniestro ya no admite evidencias."


class LimiteEvidencias(ErrorSiniestro):
    status_code = 409
    codigo = "LIMITE_EVIDENCIAS"
    mensaje = "Llegaste al máximo de evidencias de este tipo."


class EvidenciaDemasiadoGrande(ErrorSiniestro):
    status_code = 413
    codigo = "EVIDENCIA_DEMASIADO_GRANDE"
    mensaje = "El archivo supera el tamaño permitido."


class FormatoNoSoportado(ErrorSiniestro):
    status_code = 415
    codigo = "FORMATO_NO_SOPORTADO"
    mensaje = "Las fotos deben ser JPEG y los videos MP4."


class TipoEvidenciaNoPermitido(ErrorSiniestro):
    status_code = 422
    codigo = "TIPO_EVIDENCIA_NO_PERMITIDO"
    mensaje = "Este tipo de siniestro no admite videos."


class EvidenciaNoEncontrada(ErrorSiniestro):
    status_code = 404
    codigo = "EVIDENCIA_NO_ENCONTRADA"
    mensaje = "No encontramos la evidencia."


class CargaNoEncontrada(ErrorSiniestro):
    status_code = 409
    codigo = "CARGA_NO_ENCONTRADA"
    mensaje = "El archivo todavía no se ha subido."


class CargaExpirada(ErrorSiniestro):
    status_code = 409
    codigo = "CARGA_EXPIRADA"
    mensaje = "La carga venció. Solicita una nueva."


class EvidenciaRechazada(ErrorSiniestro):
    status_code = 422
    codigo = "EVIDENCIA_RECHAZADA"
    mensaje = "El archivo no coincide con lo declarado y se descartó."


class TransicionInvalida(ErrorSiniestro):
    status_code = 409
    codigo = "TRANSICION_INVALIDA"
    mensaje = "La evidencia ya no admite este cambio."
