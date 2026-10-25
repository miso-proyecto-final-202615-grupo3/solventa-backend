from collections.abc import AsyncGenerator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.kyc import KycVerifier
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.application.ports.consentimiento_cache import ConsentimientoCachePort
from src.application.ports.consentimiento_biometrico import ConsentimientoBiometricoPort
from src.application.ports.liveness import LivenessVerificationPort
from src.application.use_cases.iniciar_activacion_movil_use_case import (
    IniciarActivacionMovilUseCase,
)
from src.application.use_cases.verificar_activacion_movil_use_case import VerificarActivacionMovilUseCase
from src.application.use_cases.gestionar_consentimiento_use_case import (
    GestionarConsentimientoUseCase,
)
from src.application.use_cases.consultar_auditoria_consentimiento_use_case import (
    ConsultarAuditoriaConsentimientoUseCase,
)
from src.application.use_cases.registrar_cliente_use_case import RegistrarClienteUseCase
from src.application.use_cases.verificar_kyc_use_case import VerificarKycUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.clientes.repositories import ClienteRepository
from src.infrastructure.gateways.cognito_identity_provider import CognitoIdentityProvider
from src.infrastructure.gateways.kyc_http_client import KycHttpClient
from src.infrastructure.gateways.noop_identity_provider import NoopIdentityProvider
from src.infrastructure.gateways.consentimiento_biometrico_permisivo import (
    ConsentimientoBiometricoPermisivo,
)
from src.infrastructure.gateways.http_liveness_adapter_client import (
    HttpLivenessAdapterClient,
)
from src.infrastructure.cache.consentimiento_cache import ConsentimientoCache
from src.infrastructure.persistence.auditoria_consentimiento_repository_impl import (
    SqlAlchemyAuditoriaConsentimientoRepository,
)
from src.infrastructure.persistence.cliente_repository_impl import (
    SqlAlchemyClienteRepository,
)
from src.infrastructure.persistence.consentimiento_repository_impl import (
    SqlAlchemyConsentimientoRepository,
)
from src.infrastructure.persistence.activacion_movil_repository_impl import (
    SqlAlchemyActivacionMovilRepository,
)

_redis_client = Redis.from_url(
    settings.REDIS_ENDPOINT,
    password=settings.REDIS_AUTH_TOKEN or None,
    decode_responses=True,
)
_consentimiento_cache = ConsentimientoCache(
    _redis_client, settings.CONSENT_CACHE_TTL_SECONDS
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_cliente_repository(
    db: AsyncSession = Depends(get_db),
) -> ClienteRepository:
    return SqlAlchemyClienteRepository(db)


def get_consentimiento_repository(
    db: AsyncSession = Depends(get_db),
) -> SqlAlchemyConsentimientoRepository:
    return SqlAlchemyConsentimientoRepository(db)


def get_consentimiento_cache() -> ConsentimientoCachePort:
    return _consentimiento_cache


async def cerrar_consentimiento_cache() -> None:
    await _consentimiento_cache.cerrar()


def get_gestionar_consentimiento_use_case(
    repository: SqlAlchemyConsentimientoRepository = Depends(
        get_consentimiento_repository
    ),
    cliente_repository: ClienteRepository = Depends(get_cliente_repository),
    cache: ConsentimientoCachePort = Depends(get_consentimiento_cache),
) -> GestionarConsentimientoUseCase:
    return GestionarConsentimientoUseCase(
        repository,
        cliente_repository,
        cache,
        settings.CONSENT_TERMS_VERSION,
    )


def get_consultar_auditoria_consentimiento_use_case(
    db: AsyncSession = Depends(get_db),
) -> ConsultarAuditoriaConsentimientoUseCase:
    return ConsultarAuditoriaConsentimientoUseCase(
        SqlAlchemyAuditoriaConsentimientoRepository(db)
    )


def get_identity_provider() -> IdentityProvider:
    if settings.COGNITO_ENABLED:
        return CognitoIdentityProvider()
    return NoopIdentityProvider()


def get_registrar_cliente_use_case(
    repository: ClienteRepository = Depends(get_cliente_repository),
    identity_provider: IdentityProvider = Depends(get_identity_provider),
    cache: ConsentimientoCachePort = Depends(get_consentimiento_cache),
) -> RegistrarClienteUseCase:
    return RegistrarClienteUseCase(repository, identity_provider, cache)


def get_autenticar_cliente_use_case(
    identity_provider: IdentityProvider = Depends(get_identity_provider),
) -> AutenticarClienteUseCase:
    return AutenticarClienteUseCase(identity_provider)


def get_kyc_verifier() -> KycVerifier:
    return KycHttpClient()


def get_liveness_verifier() -> LivenessVerificationPort:
    return HttpLivenessAdapterClient()


def get_consentimiento_biometrico() -> ConsentimientoBiometricoPort:
    return ConsentimientoBiometricoPermisivo(settings.REQUIRE_BIOMETRIC_CONSENT)


def get_iniciar_activacion_movil_use_case(
    db: AsyncSession = Depends(get_db),
    consentimiento: ConsentimientoBiometricoPort = Depends(get_consentimiento_biometrico),
    liveness: LivenessVerificationPort = Depends(get_liveness_verifier),
) -> IniciarActivacionMovilUseCase:
    return IniciarActivacionMovilUseCase(
        SqlAlchemyClienteRepository(db),
        SqlAlchemyActivacionMovilRepository(db),
        consentimiento,
        liveness,
        db.commit,
    )


def get_verificar_activacion_movil_use_case(
    db: AsyncSession = Depends(get_db), liveness: LivenessVerificationPort = Depends(get_liveness_verifier),
) -> VerificarActivacionMovilUseCase:
    return VerificarActivacionMovilUseCase(
        SqlAlchemyClienteRepository(db), SqlAlchemyActivacionMovilRepository(db), liveness, db.commit
    )


def get_verificar_kyc_use_case(
    repository: ClienteRepository = Depends(get_cliente_repository),
    kyc_verifier: KycVerifier = Depends(get_kyc_verifier),
) -> VerificarKycUseCase:
    return VerificarKycUseCase(repository, kyc_verifier)
