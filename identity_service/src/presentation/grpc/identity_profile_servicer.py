import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import grpc

from src.application.use_cases.gestionar_consentimiento_use_case import (
    ConsentimientoNoOtorgadoError,
    GestionarConsentimientoUseCase,
    PerfilClienteNoEncontradoError,
)
from src.presentation.grpc import identity_profile_pb2, identity_profile_pb2_grpc

logger = logging.getLogger(__name__)

UseCaseFactory = Callable[
    [], AbstractAsyncContextManager[GestionarConsentimientoUseCase]
]

_CAMPOS_PERFIL = (
    "id",
    "nombres",
    "apellidos",
    "tipo_documento",
    "numero_identificacion",
    "correo",
    "fecha_nacimiento",
    "pais_residencia",
    "telefono",
    "estado_kyc",
)


class IdentityProfileServicer(identity_profile_pb2_grpc.IdentityProfileServicer):
    """Expone la consulta de perfil a otros microservicios (p. ej. quotingengine)."""

    def __init__(self, use_case_factory: UseCaseFactory) -> None:
        self._use_case_factory = use_case_factory

    async def ObtenerPerfilCliente(self, request, context):
        try:
            cliente_id = uuid.UUID(request.cliente_id)
        except ValueError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "cliente_id inválido."
            )

        try:
            async with self._use_case_factory() as use_case:
                perfil = await use_case.obtener_perfil_cliente(cliente_id)
        except ConsentimientoNoOtorgadoError:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "El cliente no ha autorizado la consulta de su perfil.",
            )
        except PerfilClienteNoEncontradoError:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, "Cliente no encontrado."
            )

        return identity_profile_pb2.PerfilClienteResponse(
            **{campo: str(perfil.get(campo) or "") for campo in _CAMPOS_PERFIL}
        )
