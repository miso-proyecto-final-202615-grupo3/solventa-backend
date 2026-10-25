from src.infrastructure.persistence.models import (
    DispositivoVinculadoModel,
    IntentoPruebaVidaModel,
    SesionActivacionModel,
)


def test_modelos_de_activacion_no_persisten_evidencia_biometrica():
    session_columns = set(SesionActivacionModel.__table__.columns.keys())
    attempt_columns = set(IntentoPruebaVidaModel.__table__.columns.keys())
    device_columns = set(DispositivoVinculadoModel.__table__.columns.keys())

    assert session_columns == {
        "id", "cliente_id", "installation_id", "plataforma", "modelo",
        "version_so", "tipo_captura", "estado", "creada_en", "expira_en",
    }
    assert attempt_columns == {
        "id", "cliente_id", "sesion_id", "installation_id", "estado", "folio",
        "motivo", "creado_en", "resuelto_en",
    }
    assert "ultimo_acceso_en" in device_columns
    assert not {"frame", "frames", "nonce", "evidencia"} & (
        session_columns | attempt_columns | device_columns
    )


def test_modelos_de_activacion_tienen_indices_de_consulta_requeridos():
    assert {"installation_id", "estado"} == {
        column.name
        for index in SesionActivacionModel.__table__.indexes
        for column in index.columns
    }
    assert {"cliente_id", "creado_en"} == {
        column.name
        for index in IntentoPruebaVidaModel.__table__.indexes
        for column in index.columns
    }
