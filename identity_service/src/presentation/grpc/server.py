import logging

import grpc

from src.presentation.grpc import identity_profile_pb2_grpc
from src.presentation.grpc.identity_profile_servicer import (
    IdentityProfileServicer,
    UseCaseFactory,
)

logger = logging.getLogger(__name__)


async def iniciar_servidor_grpc(
    use_case_factory: UseCaseFactory, port: int
) -> grpc.aio.Server:
    server = grpc.aio.server()
    identity_profile_pb2_grpc.add_IdentityProfileServicer_to_server(
        IdentityProfileServicer(use_case_factory), server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("Servidor gRPC de identidad escuchando en el puerto %s", port)
    return server
