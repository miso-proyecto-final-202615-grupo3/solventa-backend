from decimal import Decimal, InvalidOperation
import uuid

import grpc

from src.application.ports.perfilamiento import (
    ClienteCotizacionNoEncontradoError,
    ConsentimientoNoActivoError,
    OpenFinanceNoDisponibleError,
    PerfilamientoNoDisponibleError,
    PerfilFinancieroProvider,
)
from src.domain.pricing import PerfilFinanciero
from src.infrastructure.grpc import perfilamiento_pb2, perfilamiento_pb2_grpc


class PerfilamientoGrpcClient(PerfilFinancieroProvider):
    def __init__(
        self,
        channel: grpc.aio.Channel,
        timeout_seconds: float = 0.25,
    ) -> None:
        self.stub = perfilamiento_pb2_grpc.PerfilamientoStub(channel)
        self.timeout_seconds = min(timeout_seconds, 0.7)

    async def obtener_perfil_financiero(
        self, cliente_id: uuid.UUID
    ) -> PerfilFinanciero:
        try:
            response = await self.stub.ObtenerPerfilFinanciero(
                perfilamiento_pb2.SolicitudPerfilFinanciero(
                    cliente_id=str(cliente_id)
                ),
                timeout=self.timeout_seconds,
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.PERMISSION_DENIED:
                raise ConsentimientoNoActivoError from exc
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                raise ClienteCotizacionNoEncontradoError from exc
            if exc.code() in {
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
            }:
                raise PerfilamientoNoDisponibleError from exc
            raise

        if not response.proveedor_disponible:
            raise OpenFinanceNoDisponibleError

        try:
            return PerfilFinanciero(
                ingreso_mensual=Decimal(response.ingreso_mensual),
                ahorros_liquidos=Decimal(response.ahorros_liquidos),
                dti_pct=Decimal(response.dti_pct),
                sobregiros_12_meses=response.sobregiros_12_meses,
                score=response.score,
            )
        except (InvalidOperation, ValueError) as exc:
            raise PerfilamientoNoDisponibleError from exc
