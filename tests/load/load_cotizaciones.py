"""Prueba de carga de creación de cotizaciones mediante BFF Web."""

import argparse
import os
import sqlite3
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

PRODUCTO = "VIDA_HIPOTECARIO"
TIMEOUT = 30
DIRECTORIO = Path(__file__).resolve().parent


def positivo(valor):
    numero = int(valor)
    if numero <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return numero


def url_bff(entorno):
    variable = f"SYSTEM_TESTS_{entorno.upper()}_BASE_URL"
    valor = os.getenv(variable)
    if not valor:
        raise ValueError(f"{variable} no está definida en el entorno ni en tests/load/.env")
    return valor.rstrip("/") + "/api/v1/bff-web"


def respuesta_json(respuesta, estado, operacion):
    if respuesta.status_code != estado:
        raise RuntimeError(f"{operacion}: HTTP {respuesta.status_code}, se esperaba {estado}")
    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise RuntimeError(f"{operacion}: respuesta JSON inválida") from exc
    if not isinstance(datos, dict):
        raise RuntimeError(f"{operacion}: se esperaba un objeto JSON")
    return datos


def preparar_clientes(bff, cantidad):
    producto = respuesta_json(
        requests.get(f"{bff}/productos/{PRODUCTO}", timeout=TIMEOUT),
        200, "consulta del producto",
    )
    if producto.get("codigo") != PRODUCTO or not producto.get("producto_id"):
        raise RuntimeError("La consulta del producto no devolvió el producto esperado")
    clientes = []
    for _ in range(cantidad):
        identificador = uuid.uuid4().hex
        datos = {
            "nombres": "Cliente",
            "apellidos": "Prueba Sistema",
            "tipo_documento": "CC",
            "numero_identificacion": str(uuid.uuid4().int)[:10],
            "correo": f"cliente-prueba-{identificador}@example.com",
            "password": "SystemTest123!",
            "consentimiento_datos": True,
            "fecha_nacimiento": "1990-05-15",
            "pais_residencia": "Colombia",
            "telefono": "+573001234567",
        }
        registro = respuesta_json(
            requests.post(f"{bff}/clientes/registro", json=datos, timeout=TIMEOUT),
            201, "registro de cliente",
        )
        if not registro.get("id"):
            raise RuntimeError("El registro no devolvió el ID del cliente")
        autenticacion = respuesta_json(
            requests.post(
                f"{bff}/clientes/autenticar",
                json={"correo": datos["correo"], "password": datos["password"]},
                timeout=TIMEOUT,
            ),
            200, "autenticación de cliente",
        )
        if not autenticacion.get("access_token"):
            raise RuntimeError("La autenticación no devolvió un token de acceso")
        clientes.append((registro["id"], autenticacion["access_token"]))
    return clientes


def ahora():
    return datetime.now(timezone.utc).isoformat()


def cotizar(url, cliente, numero):
    cliente_id, token = cliente
    inicio = ahora()
    reloj = time.perf_counter()
    estado = None
    exitoso = False
    cotizacion_id = None
    error = None
    try:
        respuesta = requests.post(
            url,
            json={
                "cliente_id": cliente_id,
                "producto_codigo": PRODUCTO,
                "parametros": {
                    "saldo_credito": 200000000,
                    "ubicacion": {"municipio": "Bogotá D.C.", "zona": "URBANA", "estrato": 4},
                },
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        duracion_ms = (time.perf_counter() - reloj) * 1000
        estado = respuesta.status_code
        if estado != 201:
            error = f"HTTP {estado}"
        else:
            try:
                datos = respuesta.json()
            except ValueError:
                error = "Respuesta JSON inválida"
            else:
                if not isinstance(datos, dict):
                    error = "La respuesta no es un objeto JSON"
                elif not datos.get("cotizacion_id"):
                    error = "La respuesta no incluye cotizacion_id"
                elif datos.get("cliente_id") != cliente_id or datos.get("producto_codigo") != PRODUCTO:
                    error = "La respuesta no corresponde al cliente o producto solicitado"
                else:
                    cotizacion_id = str(datos["cotizacion_id"])
                    exitoso = True
    except requests.RequestException as exc:
        duracion_ms = (time.perf_counter() - reloj) * 1000
        error = type(exc).__name__
    return (numero, str(cliente_id), inicio, duracion_ms, estado, int(exitoso), cotizacion_id, error)


def inicializar(conexion):
    conexion.executescript("""
        CREATE TABLE IF NOT EXISTS ejecuciones (
            id TEXT PRIMARY KEY, entorno TEXT NOT NULL, servicio TEXT NOT NULL,
            hilos INTEGER NOT NULL, max_invocaciones INTEGER NOT NULL,
            inicio TEXT NOT NULL, fin TEXT, duracion_segundos REAL
        );
        CREATE TABLE IF NOT EXISTS resultados (
            ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
            numero INTEGER NOT NULL, cliente_id TEXT NOT NULL, inicio TEXT NOT NULL,
            duracion_ms REAL NOT NULL, estado_http INTEGER, exitoso INTEGER NOT NULL,
            cotizacion_id TEXT, error TEXT,
            PRIMARY KEY (ejecucion_id, numero)
        );
    """)


def ejecutar(conexion, entorno, hilos, maximo, url, clientes):
    ejecucion_id = str(uuid.uuid4())
    conexion.execute(
        "INSERT INTO ejecuciones (id, entorno, servicio, hilos, max_invocaciones, inicio) VALUES (?, ?, ?, ?, ?, ?)",
        (ejecucion_id, entorno, "bff-web", hilos, maximo, ahora()),
    )
    conexion.commit()
    reloj = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=hilos) as executor:
            pendientes = set()
            siguiente = 1
            while siguiente <= min(hilos, maximo):
                pendientes.add(executor.submit(cotizar, url, clientes[(siguiente - 1) % len(clientes)], siguiente))
                siguiente += 1
            while pendientes:
                terminadas, pendientes = wait(pendientes, return_when=FIRST_COMPLETED)
                for futura in terminadas:
                    resultado = futura.result()
                    conexion.execute(
                        "INSERT INTO resultados VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (ejecucion_id, *resultado),
                    )
                    conexion.commit()
                    if siguiente <= maximo:
                        pendientes.add(executor.submit(cotizar, url, clientes[(siguiente - 1) % len(clientes)], siguiente))
                        siguiente += 1
    finally:
        conexion.execute(
            "UPDATE ejecuciones SET fin = ?, duracion_segundos = ? WHERE id = ?",
            (ahora(), time.perf_counter() - reloj, ejecucion_id),
        )
        conexion.commit()
    return ejecucion_id


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="Configura las URLs en tests/load/.env; las variables de entorno tienen prioridad.",
    )
    parser.add_argument(
        "entorno", nargs="?", choices=("dev", "prod"), default="dev",
        help="entorno de ejecución",
    )
    parser.add_argument("--hilos", type=positivo, default=4, help="número máximo de hilos")
    parser.add_argument(
        "--clientes", type=positivo, default=4,
        help="cantidad de clientes nuevos para el pool",
    )
    parser.add_argument(
        "--max-invocaciones", type=positivo, default=100,
        help="número máximo de peticiones de cotización",
    )
    parser.add_argument(
        "--db", type=Path, default=DIRECTORIO / "resultados.sqlite3",
        help="archivo SQLite donde se guardan los resultados",
    )
    args = parser.parse_args()
    load_dotenv(DIRECTORIO / ".env")
    bff = url_bff(args.entorno)
    print(f"Preparando {args.clientes} clientes y verificando el producto...")
    clientes = preparar_clientes(bff, args.clientes)
    with sqlite3.connect(args.db) as conexion:
        inicializar(conexion)
        ejecucion = ejecutar(
            conexion, args.entorno, args.hilos, args.max_invocaciones,
            f"{bff}/cotizaciones", clientes,
        )
        total, exitos = conexion.execute(
            "SELECT COUNT(*), COALESCE(SUM(exitoso), 0) FROM resultados WHERE ejecucion_id = ?",
            (ejecucion,),
        ).fetchone()
    print(f"Ejecución {ejecucion}: {total} peticiones, {exitos} exitosas. SQLite: {args.db}")
    return 0 if total == args.max_invocaciones and exitos == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
