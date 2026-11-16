import pytest
from pydantic import ValidationError

from src.core.config import Settings, settings
from src.infrastructure.gateways.cognito_identity_provider import (
    CognitoIdentityProvider,
)
from src.infrastructure.gateways.noop_identity_provider import NoopIdentityProvider
from src.infrastructure.storage.documento_verificacion_local_repository import (
    LocalDocumentoVerificacionRepository,
)
from src.infrastructure.storage.documento_verificacion_s3_repository import (
    S3DocumentoVerificacionRepository,
)
from src.presentation.dependencies import (
    get_documento_verificacion_repository,
    get_identity_provider,
)


async def test_get_identity_provider_devuelve_noop_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_ENABLED", False)

    assert isinstance(get_identity_provider(), NoopIdentityProvider)


async def test_get_identity_provider_devuelve_cognito_cuando_esta_habilitado(
    monkeypatch,
):
    monkeypatch.setattr(settings, "COGNITO_ENABLED", True)

    assert isinstance(get_identity_provider(), CognitoIdentityProvider)


@pytest.fixture
def limpiar_cache_documentos():
    get_documento_verificacion_repository.cache_clear()
    yield
    get_documento_verificacion_repository.cache_clear()


def test_almacenamiento_s3_es_el_predeterminado(monkeypatch):
    monkeypatch.delenv("KYC_DOCUMENT_STORAGE", raising=False)
    assert Settings(_env_file=None).KYC_DOCUMENT_STORAGE == "s3"


@pytest.mark.parametrize("tipo", ["local", "s3"])
def test_configura_almacenamiento_por_variable_de_entorno(monkeypatch, tipo):
    monkeypatch.setenv("KYC_DOCUMENT_STORAGE", tipo)
    assert Settings(_env_file=None).KYC_DOCUMENT_STORAGE == tipo


def test_configuracion_de_almacenamiento_invalida_falla(monkeypatch):
    monkeypatch.setenv("KYC_DOCUMENT_STORAGE", "invalido")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_selecciona_almacenamiento_local_sin_crear_cliente_s3(
    monkeypatch, limpiar_cache_documentos
):
    def s3_no_debe_crearse():
        raise AssertionError("El cliente S3 no debe inicializarse en modo local.")

    monkeypatch.setattr(settings, "KYC_DOCUMENT_STORAGE", "local")
    monkeypatch.setattr(
        "src.presentation.dependencies.S3DocumentoVerificacionRepository", s3_no_debe_crearse
    )

    repo = get_documento_verificacion_repository()

    assert isinstance(repo, LocalDocumentoVerificacionRepository)
    assert get_documento_verificacion_repository() is repo


def test_selecciona_almacenamiento_s3(monkeypatch, limpiar_cache_documentos):
    sentinel = object()
    monkeypatch.setattr(settings, "KYC_DOCUMENT_STORAGE", "s3")
    monkeypatch.setattr(
        "src.infrastructure.storage.documento_verificacion_s3_repository.boto3.client",
        lambda service, region_name: sentinel,
    )

    repo = get_documento_verificacion_repository()
    assert isinstance(repo, S3DocumentoVerificacionRepository)
    assert repo._client is sentinel


def test_configuracion_invalida_no_selecciona_s3(monkeypatch, limpiar_cache_documentos):
    monkeypatch.setattr(settings, "KYC_DOCUMENT_STORAGE", "invalido")

    with pytest.raises(ValueError):
        get_documento_verificacion_repository()