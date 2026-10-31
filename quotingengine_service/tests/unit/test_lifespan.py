import src.main as main


class _EngineSinBD:
    def begin(self):
        raise RuntimeError("base de datos no disponible")


class _SesionSinBD:
    async def __aenter__(self):
        raise RuntimeError("base de datos no disponible")

    async def __aexit__(self, *args):
        return False


async def test_lifespan_no_rompe_por_falta_de_bd(monkeypatch):
    monkeypatch.setattr(main, "engine", _EngineSinBD())
    monkeypatch.setattr(main, "SessionLocal", _SesionSinBD)
    cerrado = []

    async def cerrar():
        cerrado.append(True)

    async def inicializar():
        return None

    monkeypatch.setattr(main, "cerrar_recursos", cerrar)
    monkeypatch.setattr(main, "inicializar_recursos", inicializar)

    async with main.lifespan(None):
        pass

    assert cerrado == [True]
