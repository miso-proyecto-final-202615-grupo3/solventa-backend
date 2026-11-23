"""Analiza una ejecución de carga y genera un informe HTML y gráficos SVG."""

import argparse
import math
import sqlite3
import statistics
import uuid
from collections import Counter
from html import escape
from pathlib import Path

DIRECTORIO = Path(__file__).resolve().parent


def percentil(valores, porcentaje):
    ordenados = sorted(valores)
    posicion = (len(ordenados) - 1) * porcentaje / 100
    inferior = math.floor(posicion)
    superior = math.ceil(posicion)
    return ordenados[inferior] + (ordenados[superior] - ordenados[inferior]) * (posicion - inferior)


def svg_estados(estados):
    altura = 100 + 35 * len(estados)
    maximo = max(estados.values())
    elementos = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{altura}" viewBox="0 0 800 {altura}">',
        f'<rect width="800" height="{altura}" fill="white"/>',
        '<text x="400" y="25" text-anchor="middle" font-family="sans-serif">Distribución de códigos HTTP</text>',
    ]
    for i, (estado, cantidad) in enumerate(sorted(estados.items())):
        y = 55 + i * 35
        ancho = 500 * cantidad / maximo
        elementos.append(f'<text x="165" y="{y + 17}" text-anchor="end" font-family="sans-serif" font-size="12">{escape(estado)}</text>')
        elementos.append(f'<rect x="175" y="{y}" width="{ancho:.2f}" height="22" fill="#2878b5"/>')
        elementos.append(f'<text x="{180 + ancho:.2f}" y="{y + 17}" font-family="sans-serif" font-size="12">{cantidad}</text>')
    elementos.append("</svg>")
    return "\n".join(elementos)


def svg_resultados(exitos, fallos):
    total = exitos + fallos
    elementos = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">',
        '<rect width="800" height="300" fill="white"/>',
        '<text x="400" y="25" text-anchor="middle" font-family="sans-serif">Peticiones exitosas y fallidas</text>',
    ]
    angulo = -math.pi / 2
    for i, (etiqueta, cantidad, color) in enumerate(
        (("Exitosas", exitos, "#2878b5"), ("Fallidas", fallos, "#d62728"))
    ):
        proporcion = cantidad / total
        if cantidad == total:
            elementos.append(f'<circle cx="200" cy="155" r="100" fill="{color}"/>')
        elif cantidad:
            fin = angulo + 2 * math.pi * proporcion
            x1, y1 = 200 + 100 * math.cos(angulo), 155 + 100 * math.sin(angulo)
            x2, y2 = 200 + 100 * math.cos(fin), 155 + 100 * math.sin(fin)
            arco_grande = int(proporcion > 0.5)
            elementos.append(
                f'<path d="M 200 155 L {x1:.3f} {y1:.3f} '
                f'A 100 100 0 {arco_grande} 1 {x2:.3f} {y2:.3f} Z" fill="{color}"/>'
            )
            angulo = fin
        y = 130 + i * 35
        elementos.append(f'<rect x="360" y="{y - 14}" width="16" height="16" fill="{color}"/>')
        elementos.append(
            f'<text x="385" y="{y}" font-family="sans-serif" font-size="14">'
            f'{etiqueta}: {cantidad} ({proporcion * 100:.2f} %)</text>'
        )
    elementos.append("</svg>")
    return "\n".join(elementos)


def svg_histograma(tiempos):
    minimo, maximo = min(tiempos), max(tiempos)
    ancho_intervalo = (maximo - minimo) / 10 if maximo > minimo else 1
    cuentas = [0] * 10
    for tiempo in tiempos:
        indice = min(9, int((tiempo - minimo) / ancho_intervalo))
        cuentas[indice] += 1
    altura_maxima = max(cuentas)
    elementos = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">',
        '<rect width="800" height="400" fill="white"/>',
        '<text x="400" y="25" text-anchor="middle" font-family="sans-serif">Distribución de latencias</text>',
        '<path d="M70 45 V330 H760" fill="none" stroke="black"/>',
    ]
    for i, cuenta in enumerate(cuentas):
        x = 75 + i * 68
        alto = 270 * cuenta / altura_maxima
        elementos.append(f'<rect x="{x}" y="{330-alto:.2f}" width="55" height="{alto:.2f}" fill="#2878b5"/>')
        elementos.append(f'<text x="{x+27}" y="{322-alto:.2f}" text-anchor="middle" font-size="11">{cuenta}</text>')
        etiqueta = minimo + i * ancho_intervalo
        elementos.append(f'<text x="{x+27}" y="347" text-anchor="middle" font-size="10">{etiqueta:.0f}</text>')
    elementos.extend([
        '<text x="400" y="385" text-anchor="middle" font-family="sans-serif" font-size="12">Inicio del intervalo (ms)</text>',
        '<text x="18" y="190" transform="rotate(-90 18 190)" text-anchor="middle" font-family="sans-serif" font-size="12">Peticiones</text>',
        "</svg>",
    ])
    return "\n".join(elementos)


def svg_serie(resultados):
    maximo = max(fila["duracion_ms"] for fila in resultados) or 1
    elementos = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">',
        '<rect width="800" height="400" fill="white"/>',
        '<text x="400" y="25" text-anchor="middle" font-family="sans-serif">Latencia por petición</text>',
        '<path d="M70 45 V330 H760" fill="none" stroke="black"/>',
        f'<text x="65" y="50" text-anchor="end" font-size="11">{maximo:.1f}</text>',
        '<text x="65" y="330" text-anchor="end" font-size="11">0</text>',
    ]
    for indice, fila in enumerate(resultados):
        x = 70 + 690 * indice / max(1, len(resultados) - 1)
        y = 330 - 280 * fila["duracion_ms"] / maximo
        color = "#2878b5" if fila["exitoso"] else "#d62728"
        elementos.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5" fill="{color}"/>')
    elementos.extend([
        '<text x="400" y="370" text-anchor="middle" font-family="sans-serif" font-size="12">Peticiones ordenadas por inicio (azul: éxito, rojo: fallo)</text>',
        '<text x="18" y="190" transform="rotate(-90 18 190)" text-anchor="middle" font-family="sans-serif" font-size="12">Latencia (ms)</text>',
        "</svg>",
    ])
    return "\n".join(elementos)


def analizar(db, salida, ejecucion_id=None):
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conexion:
        conexion.row_factory = sqlite3.Row
        if ejecucion_id:
            ejecucion = conexion.execute("SELECT * FROM ejecuciones WHERE id = ?", (ejecucion_id,)).fetchone()
        else:
            ejecucion = conexion.execute("SELECT * FROM ejecuciones ORDER BY inicio DESC, rowid DESC LIMIT 1").fetchone()
        if ejecucion is None:
            raise ValueError("No se encontró la ejecución solicitada")
        resultados = conexion.execute(
            "SELECT * FROM resultados WHERE ejecucion_id = ? ORDER BY inicio, numero",
            (ejecucion["id"],),
        ).fetchall()
    if not resultados:
        raise ValueError("La ejecución no contiene resultados")
    try:
        identificador = str(uuid.UUID(ejecucion["id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("El ID de la ejecución no es un UUID válido") from exc
    if identificador != ejecucion["id"]:
        raise ValueError("El ID de la ejecución no es un UUID canónico")
    tiempos = [fila["duracion_ms"] for fila in resultados]
    exitos = sum(fila["exitoso"] for fila in resultados)
    estados = Counter(str(fila["estado_http"]) if fila["estado_http"] is not None else "Sin respuesta" for fila in resultados)
    errores = Counter(fila["error"] or "Sin detalle" for fila in resultados if not fila["exitoso"])
    duracion = ejecucion["duracion_segundos"]
    salida = salida / f"ejecucion-{identificador}"
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "estados_http.svg").write_text(svg_estados(estados), encoding="utf-8")
    (salida / "resultados.svg").write_text(svg_resultados(exitos, len(resultados) - exitos), encoding="utf-8")
    (salida / "latencias.svg").write_text(svg_serie(resultados), encoding="utf-8")
    (salida / "histograma.svg").write_text(svg_histograma(tiempos), encoding="utf-8")
    tasa = f"{len(resultados) / duracion:.2f} peticiones/s" if duracion and duracion > 0 else "No disponible (ejecución en curso o sin duración)"
    resumen = [
        ("Ejecución", ejecucion["id"]),
        ("Entorno / servicio", f"{ejecucion['entorno']} / {ejecucion['servicio']}"),
        ("Inicio / fin (UTC)", f"{ejecucion['inicio']} / {ejecucion['fin'] or 'en curso'}"),
        ("Hilos", ejecucion["hilos"]),
        ("Invocaciones previstas / registradas", f"{ejecucion['max_invocaciones']} / {len(resultados)}"),
        ("Duración de la ejecución", f"{duracion:.3f} s" if duracion is not None else "no disponible"),
        ("Rendimiento", tasa),
        ("Exitosas", f"{exitos} ({100 * exitos / len(resultados):.2f} %)"),
        ("Fallidas", f"{len(resultados) - exitos} ({100 * (len(resultados) - exitos) / len(resultados):.2f} %)"),
    ]
    latencias = [
        ("Mínima", f"{min(tiempos):.2f} ms"),
        ("Media", f"{statistics.mean(tiempos):.2f} ms"),
        ("Mediana", f"{statistics.median(tiempos):.2f} ms"),
        ("P95", f"{percentil(tiempos, 95):.2f} ms"),
        ("P99", f"{percentil(tiempos, 99):.2f} ms"),
        ("Máxima", f"{max(tiempos):.2f} ms"),
    ]

    def lista(pares):
        return "<ul>\n" + "\n".join(
            f"<li><strong>{escape(str(nombre))}:</strong> {escape(str(valor))}</li>"
            for nombre, valor in pares
        ) + "\n</ul>"

    lineas = [
        "<!doctype html>",
        '<html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Informe de carga: cotizaciones</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;"
        "line-height:1.5;color:#222}img{max-width:100%;height:auto}li{margin:.25rem 0}</style>",
        "</head><body>",
        "<h1>Informe de carga: cotizaciones</h1>",
        lista(resumen),
        "<h2>Latencia de todas las peticiones</h2>",
        lista(latencias),
        "<p>Los percentiles usan interpolación lineal. La latencia mide la petición HTTP completa, "
        "incluidas las fallidas; el rendimiento divide las peticiones registradas entre la duración "
        "de la fase de carga.</p>",
        "<h2>Respuestas HTTP</h2>",
        lista(sorted(estados.items())),
    ]
    if errores:
        lineas.extend(["<h2>Motivos de fallo</h2>", lista(sorted(errores.items()))])
    lineas.extend([
        "<h2>Gráficos</h2>",
        '<img src="estados_http.svg" alt="Distribución de códigos HTTP">',
        '<img src="resultados.svg" alt="Peticiones exitosas y fallidas">',
        '<img src="latencias.svg" alt="Latencia por petición">',
        '<img src="histograma.svg" alt="Distribución de latencias">',
        "</body></html>",
    ])
    informe = salida / "informe.html"
    informe.write_text("\n".join(lineas), encoding="utf-8")
    return informe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DIRECTORIO / "resultados.sqlite3")
    parser.add_argument("--ejecucion", help="UUID de la ejecución; por defecto se analiza la más reciente")
    parser.add_argument(
        "--salida", type=Path, default=DIRECTORIO / "informe",
        help="directorio donde se crea la carpeta ejecucion-<id>",
    )
    args = parser.parse_args()
    informe = analizar(args.db, args.salida, args.ejecucion)
    print(f"Informe generado: {informe}")


if __name__ == "__main__":
    main()
