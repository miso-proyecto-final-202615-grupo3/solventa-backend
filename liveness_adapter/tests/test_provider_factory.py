import pytest

from src.application.ports import ProviderNotRegisteredError
from src.infrastructure.configuration import InMemoryActiveProviderConfiguration
from src.infrastructure.provider_factory import LivenessProviderFactory
from src.infrastructure.providers.propio import PropioProvider


def test_factory_registra_y_obtiene_el_proveedor_propio():
    factory = LivenessProviderFactory([PropioProvider()])

    assert factory.registered() == ("propio",)
    assert factory.get("propio").name == "propio"


def test_factory_rechaza_un_proveedor_no_registrado():
    with pytest.raises(ProviderNotRegisteredError):
        LivenessProviderFactory([PropioProvider()]).get("desconocido")


def test_la_configuracion_activa_se_puede_cambiar_sin_recrear_la_fabrica():
    configuration = InMemoryActiveProviderConfiguration("propio")

    configuration.set_active_provider("propio")

    assert configuration.get_active_provider() == "propio"


def test_propio_rechaza_fotogramas_repetidos():
    provider = PropioProvider()
    repeated = b"\xff\xd8\xffcontenido"

    result = provider.verify({}, {
        "frame_inicio": repeated,
        "frame_gesto": repeated,
        "frame_fin": repeated,
    })

    assert result.approved is False
    assert result.reason == "CAPTURA_INVALIDA"
