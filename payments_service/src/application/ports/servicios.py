class ServicioNoDisponibleError(Exception):
    """Un servicio del que depende el pago no respondió o devolvió una respuesta inválida."""

    def __init__(self, servicio: str, detalle: str = "") -> None:
        self.servicio = servicio
        super().__init__(f"{servicio}: {detalle}" if detalle else servicio)
