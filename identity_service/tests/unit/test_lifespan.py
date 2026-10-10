import src.main as main


class _EngineSinBD:
    def begin(self):
        raise RuntimeError("base de datos no disponible")


async def test_lifespan_no_rompe_por_falta_de_bd(monkeypatch):
    monkeypatch.setattr(main, "engine", _EngineSinBD())

    async with main.lifespan(None):
        pass