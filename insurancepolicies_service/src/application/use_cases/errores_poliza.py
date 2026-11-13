class PolizaNoEncontradaError(Exception):
    pass


class AccesoPolizaDenegadoError(Exception):
    """La póliza existe pero pertenece a otro cliente."""
