import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

from src.application.ports.unit_of_work import UnitOfWork
from src.application.pricing.registry import PricingStrategyRegistry
from src.application.pricing.strategy import (
    ContextoPricing,
    PricingStrategy,
    ResultadoPricing,
    SenalesPricing,
)
from src.application.services.regla_rating_resolver import ReglaRatingResolver
from src.application.use_cases.consultar_catalogo_use_case import (
    ProductoNoEncontradoError,
)
from src.domain.auditoria.entities import AuditoriaDecision
from src.domain.auditoria.repositories import AuditoriaDecisionRepository
from src.domain.cotizaciones.entities import Cotizacion, CotizacionCobertura
from src.domain.cotizaciones.repositories import (
    CotizacionCoberturaRepository,
    CotizacionRepository,
)
from src.domain.productos.entities import Cobertura, EstadoProducto
from src.domain.productos.repositories import (
    CoberturaRepository,
    ProductoSeguroRepository,
)
from src.domain.reglas_rating.entities import ReglaRating

TIPO_DECISION_RATING = "RATING"
_CENTAVOS = Decimal("0.01")


class ReglaRatingNoDisponibleError(Exception):
    pass


class ParametrosInvalidosError(Exception):
    def __init__(self, errores: list[str]) -> None:
        super().__init__("; ".join(errores))
        self.errores = errores


class CotizacionNoEncontradaError(Exception):
    pass


@dataclass(frozen=True)
class DetalleCotizacion:
    cotizacion: Cotizacion
    producto_codigo: str
    coberturas: list[tuple[CotizacionCobertura, Cobertura]]
    resultado: dict[str, Any]


class SolicitarCotizacionUseCase:
    def __init__(
        self,
        producto_repository: ProductoSeguroRepository,
        cobertura_repository: CoberturaRepository,
        cotizacion_repository: CotizacionRepository,
        cotizacion_cobertura_repository: CotizacionCoberturaRepository,
        auditoria_repository: AuditoriaDecisionRepository,
        regla_resolver: ReglaRatingResolver,
        strategies: PricingStrategyRegistry,
        unit_of_work: UnitOfWork,
        vigencia_dias: int,
    ) -> None:
        self.producto_repository = producto_repository
        self.cobertura_repository = cobertura_repository
        self.cotizacion_repository = cotizacion_repository
        self.cotizacion_cobertura_repository = cotizacion_cobertura_repository
        self.auditoria_repository = auditoria_repository
        self.regla_resolver = regla_resolver
        self.strategies = strategies
        self.unit_of_work = unit_of_work
        self.vigencia_dias = vigencia_dias

    async def solicitar(
        self,
        cliente_id: uuid.UUID,
        producto_codigo: str,
        parametros: dict[str, Any],
        socio_id: uuid.UUID | None = None,
    ) -> DetalleCotizacion:
        producto = await self.producto_repository.obtener_por_codigo(producto_codigo)
        if producto is None or producto.estado != EstadoProducto.ACTIVO:
            raise ProductoNoEncontradoError(producto_codigo)
        strategy = self.strategies.obtener(producto.codigo)

        # reglas (BD/caché) y señales externas no dependen entre sí: en paralelo
        regla, parametros, senales = await self._cargar_regla_y_senales(
            strategy, producto.producto_id, cliente_id, parametros
        )

        resultado = strategy.calcular(
            ContextoPricing(cliente_id, producto, regla, parametros, senales)
        )
        coberturas = await self.cobertura_repository.listar_activas_por_producto(
            producto.producto_id
        )

        ahora = datetime.now(timezone.utc)
        cotizacion = Cotizacion(
            cliente_id=cliente_id,
            producto_id=producto.producto_id,
            socio_id=socio_id,
            prima_total=resultado.prima_total,
            moneda=resultado.moneda,
            expira_en=ahora + timedelta(days=self.vigencia_dias),
        )
        detalles = self._distribuir_prima(cotizacion, coberturas, resultado)
        resultado_json = self._serializar_resultado(resultado)
        try:
            await self.cotizacion_repository.guardar(cotizacion)
            await self.cotizacion_cobertura_repository.guardar_todas(
                [d for d, _ in detalles]
            )
            await self.auditoria_repository.guardar(
                AuditoriaDecision(
                    cotizacion_id=cotizacion.cotizacion_id,
                    regla_rating_id=regla.regla_rating_id,
                    tipo_decision=TIPO_DECISION_RATING,
                    entradas={
                        "producto": producto.codigo,
                        "parametros": _json_seguro(parametros),
                        "regla_version": regla.version,
                        "perfil_consultado": senales.perfil is not None,
                    },
                    resultado=resultado_json,
                )
            )
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return DetalleCotizacion(cotizacion, producto.codigo, detalles, resultado_json)

    async def obtener(self, cotizacion_id: uuid.UUID) -> DetalleCotizacion:
        cotizacion = await self.cotizacion_repository.obtener_por_id(cotizacion_id)
        if cotizacion is None:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        producto = await self.producto_repository.obtener_por_id(cotizacion.producto_id)
        auditorias = await self.auditoria_repository.listar_por_cotizacion(
            cotizacion_id
        )
        detalles = await self.cotizacion_cobertura_repository.listar_por_cotizacion(
            cotizacion_id
        )
        coberturas = {
            c.cobertura_id: c
            for c in await self.cobertura_repository.listar_activas_por_producto(
                cotizacion.producto_id
            )
        }
        return DetalleCotizacion(
            cotizacion=cotizacion,
            producto_codigo=producto.codigo if producto else "",
            coberturas=[
                (d, coberturas[d.cobertura_id])
                for d in detalles
                if d.cobertura_id in coberturas
            ],
            resultado=auditorias[0].resultado if auditorias else {},
        )

    async def _cargar_regla_y_senales(
        self,
        strategy: PricingStrategy,
        producto_id: uuid.UUID,
        cliente_id: uuid.UUID,
        parametros: dict[str, Any],
    ) -> tuple[ReglaRating, dict[str, Any], SenalesPricing]:
        regla = await self.regla_resolver.obtener_vigente(producto_id)
        if regla is None:
            raise ReglaRatingNoDisponibleError(str(producto_id))
        parametros_validos = self._validar_parametros(regla, parametros)
        senales = await strategy.recolectar_senales(cliente_id, parametros_validos)
        return regla, parametros_validos, senales

    @staticmethod
    def _validar_parametros(
        regla: ReglaRating, parametros: dict[str, Any]
    ) -> dict[str, Any]:
        errores: list[str] = []
        validos: dict[str, Any] = {}
        for definicion in regla.definicion.get("parametros", []):
            nombre = definicion["nombre"]
            valor = parametros.get(nombre)
            if definicion.get("tipo") == "object":
                ubicacion = _validar_ubicacion(valor, nombre, errores)
                if ubicacion is not None:
                    validos[nombre] = ubicacion
                continue
            if valor is None or valor == "":
                if definicion.get("requerido", True):
                    errores.append(f"El parámetro '{nombre}' es obligatorio.")
                continue
            try:
                numero = Decimal(str(valor))
                if not numero.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                errores.append(f"El parámetro '{nombre}' debe ser numérico.")
                continue
            minimo = definicion.get("minimo")
            maximo = definicion.get("maximo")
            if minimo is not None and numero < Decimal(str(minimo)):
                errores.append(f"El parámetro '{nombre}' debe ser mayor o igual a {minimo}.")
            elif maximo is not None and numero > Decimal(str(maximo)):
                errores.append(f"El parámetro '{nombre}' debe ser menor o igual a {maximo}.")
            else:
                validos[nombre] = numero
        if errores:
            raise ParametrosInvalidosError(errores)
        return validos

    @staticmethod
    def _distribuir_prima(
        cotizacion: Cotizacion,
        coberturas: list[Cobertura],
        resultado: ResultadoPricing,
    ) -> list[tuple[CotizacionCobertura, Cobertura]]:
        """Reparte la prima total en partes iguales; el residuo va a la última cobertura."""
        if not coberturas:
            return []
        parte = (resultado.prima_total / len(coberturas)).quantize(
            _CENTAVOS, rounding=ROUND_DOWN
        )
        detalles = []
        acumulado = Decimal("0")
        for i, cobertura in enumerate(coberturas):
            prima = (
                resultado.prima_total - acumulado
                if i == len(coberturas) - 1
                else parte
            )
            acumulado += prima
            detalles.append(
                (
                    CotizacionCobertura(
                        cotizacion_id=cotizacion.cotizacion_id,
                        cobertura_id=cobertura.cobertura_id,
                        prima=prima,
                        limite_asegurado=cobertura.limite_asegurado,
                        deducible=cobertura.deducible,
                    ),
                    cobertura,
                )
            )
        return detalles

    @staticmethod
    def _serializar_resultado(resultado: ResultadoPricing) -> dict[str, Any]:
        return {
            "prima_base": str(resultado.prima_base),
            "ajustes": [
                {
                    "concepto": a.concepto,
                    "tipo": a.tipo.value,
                    "valor": str(a.valor),
                    "motivo": a.motivo,
                }
                for a in resultado.ajustes
            ],
            "impuestos": [
                {"concepto": i.concepto, "tasa": str(i.tasa), "valor": str(i.valor)}
                for i in resultado.impuestos
            ],
            "prima_neta": str(resultado.prima_neta),
            "prima_total": str(resultado.prima_total),
            "moneda": resultado.moneda,
            "degradaciones": list(resultado.degradaciones),
        }


def _json_seguro(parametros: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ({nested_key: str(nested_value) for nested_key, nested_value in v.items()}
            if isinstance(v, dict) else str(v))
        for k, v in parametros.items()
    }


def _validar_ubicacion(
    valor: Any, nombre: str, errores: list[str]
) -> dict[str, Any] | None:
    if not isinstance(valor, dict):
        errores.append(f"El parámetro '{nombre}' debe ser un objeto de ubicación.")
        return None
    municipio = valor.get("municipio")
    zona = valor.get("zona")
    estrato = valor.get("estrato")
    if not isinstance(municipio, str) or not 2 <= len(municipio.strip()) <= 100:
        errores.append("El municipio debe tener entre 2 y 100 caracteres.")
    if not isinstance(zona, str) or zona not in {"URBANA", "RURAL"}:
        errores.append("La zona debe ser URBANA o RURAL.")
    if isinstance(estrato, bool) or not isinstance(estrato, int) or not 1 <= estrato <= 6:
        errores.append("El estrato debe ser un entero entre 1 y 6.")
    if set(valor) - {"municipio", "zona", "estrato"}:
        errores.append("La ubicación contiene campos no permitidos.")
    if errores:
        return None
    return {"municipio": municipio.strip(), "zona": zona, "estrato": estrato}
