import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

import analizar_cotizaciones
import load_cotizaciones

DIRECTORIO = Path(__file__).resolve().parent


class LectorHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.etiquetas = []
        self.imagenes = []
        self.texto = []

    def handle_starttag(self, tag, attrs):
        self.etiquetas.append(tag)
        if tag == "img":
            self.imagenes.append(dict(attrs).get("src"))

    def handle_data(self, data):
        self.texto.append(data)


class ServidorPrueba(BaseHTTPRequestHandler):
    clientes = {}
    solicitudes = 0
    activas = 0
    concurrencia_maxima = 0
    lock = threading.Lock()

    def log_message(self, format, *args):
        pass

    def responder(self, estado, cuerpo):
        datos = json.dumps(cuerpo).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        if not self.path.startswith("/api/v1/bff-web/"):
            self.responder(404, {})
            return
        self.responder(200, {"codigo": "VIDA_HIPOTECARIO", "producto_id": "producto"})

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not self.path.startswith("/api/v1/bff-web/"):
            self.responder(404, {})
        elif self.path.endswith("/registro"):
            cliente_id = f"cliente-{len(self.clientes) + 1}"
            self.clientes[datos["correo"]] = cliente_id
            self.responder(201, {"id": cliente_id})
        elif self.path.endswith("/autenticar"):
            self.responder(200, {"access_token": self.clientes[datos["correo"]]})
        elif self.path.endswith("/cotizaciones"):
            with self.lock:
                type(self).solicitudes += 1
                numero = self.solicitudes
                type(self).activas += 1
                type(self).concurrencia_maxima = max(self.concurrencia_maxima, self.activas)
            time.sleep(0.05)
            with self.lock:
                type(self).activas -= 1
            if self.headers.get("Authorization") != f"Bearer {datos['cliente_id']}":
                self.responder(401, {})
            elif numero == 1:
                self.responder(500, {})
            elif numero == 2:
                self.responder(201, {"cliente_id": datos["cliente_id"]})
            else:
                self.responder(201, {
                    "cotizacion_id": f"cotizacion-{numero}",
                    "cliente_id": datos["cliente_id"],
                    "producto_codigo": datos["producto_codigo"],
                })
        else:
            self.responder(404, {})


class PruebaCarga(unittest.TestCase):
    def test_cli_sin_argumentos_usa_valores_predeterminados(self):
        clientes = [(f"cliente-{i}", f"token-{i}") for i in range(4)]

        def cotizar(url, cliente, numero):
            return (numero, cliente[0], load_cotizaciones.ahora(), 1.0, 201, 1, "id", None)

        with tempfile.TemporaryDirectory() as temporal:
            with (
                patch.object(load_cotizaciones, "DIRECTORIO", Path(temporal)),
                patch.object(load_cotizaciones, "url_bff", return_value="bff") as url_bff,
                patch.object(load_cotizaciones, "preparar_clientes", return_value=clientes) as preparar,
                patch.object(load_cotizaciones, "cotizar", side_effect=cotizar),
                patch.object(sys, "argv", ["load_cotizaciones.py"]),
            ):
                self.assertEqual(load_cotizaciones.main(), 0)
            url_bff.assert_called_once_with("dev")
            preparar.assert_called_once_with("bff", 4)
            with sqlite3.connect(Path(temporal) / "resultados.sqlite3") as conexion:
                self.assertEqual(
                    conexion.execute("SELECT hilos, max_invocaciones FROM ejecuciones").fetchone(),
                    (4, 100),
                )
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM resultados").fetchone()[0], 100)

    def test_cli_guarda_y_analiza_peticiones_concurrentes(self):
        ServidorPrueba.clientes = {}
        ServidorPrueba.solicitudes = 0
        ServidorPrueba.activas = 0
        ServidorPrueba.concurrencia_maxima = 0
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), ServidorPrueba)
        hilo = threading.Thread(target=servidor.serve_forever)
        hilo.start()
        self.addCleanup(hilo.join)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        with tempfile.TemporaryDirectory() as temporal:
            db = Path(temporal) / "resultados.sqlite3"
            salida = Path(temporal) / "reporte"
            url = f"http://127.0.0.1:{servidor.server_port}"
            entorno = os.environ.copy()
            entorno["SYSTEM_TESTS_DEV_BASE_URL"] = url
            resultado = subprocess.run(
                [sys.executable, str(DIRECTORIO / "load_cotizaciones.py"), "dev",
                 "--hilos", "4", "--clientes", "3", "--max-invocaciones", "13", "--db", str(db)],
                env=entorno, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(resultado.returncode, 1, resultado.stderr)
            self.assertEqual(len(ServidorPrueba.clientes), 3)
            self.assertGreater(ServidorPrueba.concurrencia_maxima, 1)
            self.assertLessEqual(ServidorPrueba.concurrencia_maxima, 4)
            with sqlite3.connect(db) as conexion:
                ejecucion = conexion.execute("SELECT id, hilos, max_invocaciones, duracion_segundos, servicio FROM ejecuciones").fetchone()
                filas = conexion.execute(
                    "SELECT numero, cliente_id, duracion_ms, estado_http, exitoso, error FROM resultados ORDER BY numero"
                ).fetchall()
            self.assertEqual(ejecucion[1:3], (4, 13))
            self.assertGreater(ejecucion[3], 0)
            self.assertEqual(ejecucion[4], "bff-web")
            self.assertEqual([fila[0] for fila in filas], list(range(1, 14)))
            self.assertEqual(len({fila[1] for fila in filas}), 3)
            self.assertTrue(all(fila[2] > 0 for fila in filas))
            self.assertEqual(sum(fila[4] for fila in filas), 11)
            self.assertEqual({fila[5] for fila in filas if not fila[4]}, {"HTTP 500", "La respuesta no incluye cotizacion_id"})
            informe = analizar_cotizaciones.analizar(db, salida, ejecucion[0])
            contenido = informe.read_text(encoding="utf-8")
            self.assertEqual(informe.name, "informe.html")
            self.assertEqual(informe.parent, salida / f"ejecucion-{ejecucion[0]}")
            lector = LectorHTML()
            lector.feed(contenido)
            texto = " ".join(lector.texto)
            self.assertIn("Invocaciones previstas / registradas:  13 / 13", texto)
            self.assertIn("Exitosas:  11", texto)
            self.assertIn("500:  1", texto)
            self.assertIn("P95:", texto)
            self.assertIn("html", lector.etiquetas)
            self.assertEqual(
                lector.imagenes,
                ["estados_http.svg", "resultados.svg", "latencias.svg", "histograma.svg"],
            )
            for imagen in lector.imagenes:
                self.assertEqual(ET.parse(informe.parent / imagen).getroot().tag, "{http://www.w3.org/2000/svg}svg")
            estados = (informe.parent / "estados_http.svg").read_text(encoding="utf-8")
            self.assertIn(">201</text>", estados)
            self.assertIn(">500</text>", estados)
            self.assertIn(">12</text>", estados)
            self.assertIn(">1</text>", estados)
            resultados = (informe.parent / "resultados.svg").read_text(encoding="utf-8")
            self.assertIn("Exitosas: 11 (84.62 %)", resultados)
            self.assertIn("Fallidas: 2 (15.38 %)", resultados)
            cli = subprocess.run(
                [sys.executable, str(DIRECTORIO / "analizar_cotizaciones.py"), "--db", str(db), "--salida", str(salida)],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)

    def test_error_de_red_y_percentiles(self):
        with patch.object(load_cotizaciones.requests, "post", side_effect=requests.Timeout("sensible")):
            resultado = load_cotizaciones.cotizar("http://example.test", ("cliente", "token"), 1)
        self.assertIsNone(resultado[4])
        self.assertEqual(resultado[5:], (0, None, "Timeout"))
        self.assertEqual(analizar_cotizaciones.percentil([0, 100], 95), 95)

    def test_urls_de_dev_y_prod_desde_archivo_de_carga(self):
        clientes = [("cliente", "token")]

        def cotizar(url, cliente, numero):
            return (numero, cliente[0], load_cotizaciones.ahora(), 1.0, 201, 1, "id", None)

        with tempfile.TemporaryDirectory() as temporal:
            directorio = Path(temporal)
            (directorio / ".env").write_text(
                "SYSTEM_TESTS_DEV_BASE_URL=https://dev.example.test\n"
                "SYSTEM_TESTS_PROD_BASE_URL=https://prod.example.test\n",
                encoding="utf-8",
            )
            for argumentos, base in (([], "https://dev.example.test"), (["prod"], "https://prod.example.test")):
                with (
                    self.subTest(argumentos=argumentos),
                    patch.dict(os.environ, {}, clear=True),
                    patch.object(load_cotizaciones, "DIRECTORIO", directorio),
                    patch.object(load_cotizaciones, "preparar_clientes", return_value=clientes) as preparar,
                    patch.object(load_cotizaciones, "cotizar", side_effect=cotizar) as solicitud,
                    patch.object(sys, "argv", ["load_cotizaciones.py", *argumentos, "--max-invocaciones", "1"]),
                ):
                    self.assertEqual(load_cotizaciones.main(), 0)
                    preparar.assert_called_once_with(f"{base}/api/v1/bff-web", 4)
                    self.assertEqual(solicitud.call_args.args[0], f"{base}/api/v1/bff-web/cotizaciones")

    def test_numero_de_clientes_debe_ser_positivo(self):
        resultado = subprocess.run(
            [sys.executable, str(DIRECTORIO / "load_cotizaciones.py"), "--clientes", "0"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("debe ser mayor que cero", resultado.stderr)

    def test_no_admite_seleccionar_servicio_directo(self):
        resultado = subprocess.run(
            [sys.executable, str(DIRECTORIO / "load_cotizaciones.py"), "dev", "insurancepolicies-service"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("unrecognized arguments", resultado.stderr)

    def test_no_admite_ambiente_local(self):
        resultado = subprocess.run(
            [sys.executable, str(DIRECTORIO / "load_cotizaciones.py"), "local"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("invalid choice", resultado.stderr)

    def test_ejecuciones_independientes_y_menos_invocaciones_que_hilos(self):
        def responder(url, json, headers, timeout):
            cuerpo = {
                "cotizacion_id": "id",
                "cliente_id": json["cliente_id"],
                "producto_codigo": json["producto_codigo"],
            }
            return SimpleNamespace(status_code=201, json=lambda: cuerpo)

        with tempfile.TemporaryDirectory() as temporal:
            db = Path(temporal) / "resultados.sqlite3"
            clientes = [(f"cliente-{i}", f"token-{i}") for i in range(4)]
            with sqlite3.connect(db) as conexion, patch.object(load_cotizaciones.requests, "post", side_effect=responder):
                load_cotizaciones.inicializar(conexion)
                primera = load_cotizaciones.ejecutar(conexion, "dev", 8, 2, "http://example.test", clientes)
                segunda = load_cotizaciones.ejecutar(conexion, "dev", 8, 1, "http://example.test", clientes)
                self.assertEqual(conexion.execute(
                    "SELECT COUNT(*), SUM(exitoso) FROM resultados WHERE ejecucion_id = ?", (primera,)
                ).fetchone(), (2, 2))
                self.assertEqual(conexion.execute(
                    "SELECT COUNT(*) FROM resultados WHERE ejecucion_id = ?", (segunda,)
                ).fetchone()[0], 1)
                conexion.execute(
                    "UPDATE resultados SET exitoso = 0, error = ? WHERE ejecucion_id = ?",
                    ("<script>alert(1)</script>", segunda),
                )
            informe = analizar_cotizaciones.analizar(db, Path(temporal) / "salida")
            contenido = informe.read_text(encoding="utf-8")
            self.assertIn(f"<strong>Ejecución:</strong> {segunda}", contenido)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", contenido)
            self.assertNotIn("<script>", contenido)
            informe_primera = analizar_cotizaciones.analizar(db, Path(temporal) / "salida", primera)
            self.assertEqual(informe_primera.parent.name, f"ejecucion-{primera}")
            self.assertEqual(informe.parent.name, f"ejecucion-{segunda}")
            self.assertTrue(informe.exists())

    def test_graficos_de_resultados_uniformes_y_sin_respuesta(self):
        for exitos, fallos in ((0, 5), (5, 0)):
            with self.subTest(exitos=exitos, fallos=fallos):
                svg = analizar_cotizaciones.svg_resultados(exitos, fallos)
                raiz = ET.fromstring(svg)
                self.assertEqual(len(raiz.findall("{http://www.w3.org/2000/svg}circle")), 1)
                self.assertEqual(len(raiz.findall("{http://www.w3.org/2000/svg}path")), 0)
                self.assertIn(f"Exitosas: {exitos} ({exitos * 20:.2f} %)", svg)
                self.assertIn(f"Fallidas: {fallos} ({fallos * 20:.2f} %)", svg)
        estados = analizar_cotizaciones.svg_estados({"201": 2, "Sin respuesta": 1})
        ET.fromstring(estados)
        self.assertIn("Sin respuesta</text>", estados)

    def test_analisis_no_crea_base_inexistente(self):
        with tempfile.TemporaryDirectory() as temporal:
            db = Path(temporal) / "inexistente.sqlite3"
            with self.assertRaises(sqlite3.OperationalError):
                analizar_cotizaciones.analizar(db, Path(temporal))
            self.assertFalse(db.exists())

    def test_analisis_rechaza_id_invalido_para_directorio(self):
        with tempfile.TemporaryDirectory() as temporal:
            db = Path(temporal) / "resultados.sqlite3"
            salida = Path(temporal) / "salida"
            with sqlite3.connect(db) as conexion:
                load_cotizaciones.inicializar(conexion)
                conexion.execute(
                    "INSERT INTO ejecuciones (id, entorno, servicio, hilos, max_invocaciones, inicio) VALUES (?, ?, ?, ?, ?, ?)",
                    ("../../otro", "dev", "bff-web", 1, 1, "2026-01-01"),
                )
                conexion.execute(
                    "INSERT INTO resultados VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("../../otro", 1, "cliente", "2026-01-01", 1, 201, 1, "id", None),
                )
            with self.assertRaisesRegex(ValueError, "UUID"):
                analizar_cotizaciones.analizar(db, salida)
            self.assertFalse(salida.exists())


if __name__ == "__main__":
    unittest.main()
