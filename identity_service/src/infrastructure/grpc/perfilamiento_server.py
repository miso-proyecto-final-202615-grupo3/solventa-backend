import uuid
from collections.abc import Awaitable, Callable

import grpc

from src.application.use_cases.obtener_perfil_financiero_use_case import (
    ClientePerfilNoEncontradoError,
    ConsentimientoNoActivoError,
)
from src.domain.perfilamiento.entities import PerfilOpenFinance
from src.infrastructure.gateways.open_finance_http_client import (
    OpenFinanceUnavailableError,
)
from src.infrastructure.grpc import perfilamiento_pb2, perfilamiento_pb2_grpc


PerfilFinancieroHandler = Callable[
    [uuid.UUID], Awaitable[PerfilOpenFinance]
]


class PerfilamientoGrpcService(perfilamiento_pb2_grpc.PerfilamientoServicer):
    def __init__(self, obtener_perfil: PerfilFinancieroHandler) -> None:
        self.obtener_perfil = obtener_perfil

    async def ObtenerPerfilFinanciero(self, request, context):
        try:
            cliente_id = uuid.UUID(request.cliente_id)
        except ValueError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "El identificador del cliente no es válido.",
            )

        try:
            perfil = await self.obtener_perfil(cliente_id)
        except ClientePerfilNoEncontradoError:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                "El cliente indicado no existe.",
            )
        except ConsentimientoNoActivoError:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "El consentimiento Open Finance no está activo.",
            )
        except OpenFinanceUnavailableError:
            return perfilamiento_pb2.RespuestaPerfilFinanciero(
                proveedor_disponible=False
            )

        return perfilamiento_pb2.RespuestaPerfilFinanciero(
            proveedor_disponible=True,
            ingreso_mensual=str(perfil.ingreso_mensual),
            ahorros_liquidos=str(perfil.ahorros_liquidos),
            dti_pct=str(perfil.dti_pct),
            sobregiros_12_meses=perfil.sobregiros_12_meses,
            score=perfil.score,
        )
