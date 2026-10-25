import uuid

from src.infrastructure.gateways.consentimiento_biometrico_permisivo import (
    ConsentimientoBiometricoPermisivo,
)


async def test_permiso_transitorio_autoriza_mientras_el_requisito_esta_desactivado():
    consentimiento = ConsentimientoBiometricoPermisivo(require_consent=False)

    assert await consentimiento.otorgado(uuid.uuid4()) is True


async def test_falla_cerrada_cuando_el_requisito_esta_activado():
    consentimiento = ConsentimientoBiometricoPermisivo(require_consent=True)

    assert await consentimiento.otorgado(uuid.uuid4()) is False
