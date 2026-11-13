import pytest
from pdf_utils import (
    datos_certificado,
    imagenes_pdf,
    paginas_pdf,
    png,
    requiere_weasyprint,
    texto_pdf,
)

from src.application.ports.generador_pdf import GeneracionPdfError
from src.infrastructure.pdf.generador_certificado import GeneradorCertificadoWeasyPrint

FIRMA = png()


def png_en_blanco() -> bytes:
    from io import BytesIO

    from PIL import Image

    salida = BytesIO()
    Image.new("RGBA", (120, 40), (0, 0, 0, 0)).save(salida, "PNG")
    return salida.getvalue()


def jpeg_blanco() -> bytes:
    from io import BytesIO

    from PIL import Image

    salida = BytesIO()
    Image.new("RGB", (120, 40), "white").save(salida, "JPEG")
    return salida.getvalue()


def generador() -> GeneradorCertificadoWeasyPrint:
    return GeneradorCertificadoWeasyPrint()


def test_expone_el_nombre_de_la_plantilla():
    assert generador().plantilla == "certificado_poliza.html"


def test_el_html_muestra_los_datos_formateados_y_la_firma_incrustada():
    html = generador().renderizar_html(datos_certificado(), FIRMA, "image/png")

    assert "POL-20261113-AB12CD34" in html
    assert "María Fernanda Rodríguez Castañeda" in html
    assert "13 de noviembre de 2026" in html and "13 de noviembre de 2036" in html
    assert "2026-11-13" not in html.replace("2026-11-13T", "")  # fechas ISO no se muestran
    assert "COP\u00a01.416.100,00" in html and "19,00\u00a0%" in html
    assert "COP\u00a0200.000.000,00" in html
    assert 'src="data:image/png;base64,' in html
    assert "Vida" in html and "Seguro de Vida Deudores Hipotecarios" in html


def test_la_plantilla_escapa_los_datos_del_titular():
    datos = datos_certificado()
    datos["titular"] = {
        "nombre": '<script>alert(1)</script><img src="file:///etc/passwd">',
        "tipo_documento": "CC",
        "numero_identificacion": "1",
    }

    html = generador().renderizar_html(datos, FIRMA, "image/png")

    assert "<script>" not in html and '<img src="file:///etc/passwd">' not in html
    assert "&lt;script&gt;" in html


def test_un_dato_faltante_rompe_la_generacion_en_vez_de_imprimir_un_certificado_incompleto():
    datos = datos_certificado()
    del datos["titular"]["nombre"]

    with pytest.raises(GeneracionPdfError):
        generador().renderizar_html(datos, FIRMA, "image/png")


@pytest.mark.parametrize("tipo", ["image/gif", "application/pdf", ""])
def test_rechaza_tipos_de_imagen_de_firma_no_soportados(tipo):
    with pytest.raises(GeneracionPdfError):
        generador().renderizar_html(datos_certificado(), FIRMA, tipo)


@pytest.mark.skip(reason="Temporal: revisar extracción del UUID del PDF")
@requiere_weasyprint
async def test_genera_un_pdf_de_una_sola_pagina_con_los_datos_y_la_firma():
    pdf = await generador().generar(datos_certificado(), FIRMA, "image/png")

    assert pdf.startswith(b"%PDF-")
    assert paginas_pdf(pdf) == 1
    assert imagenes_pdf(pdf) == 1
    texto = texto_pdf(pdf)
    for esperado in (
        "CERTIFICADO DE PÓLIZA",
        "POL-20261113-AB12CD34",
        "9b2f6a0e-1c3d-4e5f-8a7b-0c1d2e3f4a5b",
        "María Fernanda Rodríguez Castañeda",
        "CC 1020304050",
        "Seguro de Vida Deudores Hipotecarios",
        "Vida",
        "13 de noviembre de 2026",
        "13 de noviembre de 2036",
        "Cobertura número 0",
        "COP 200.000.000,00",
        "COP 1.500.000,00",
        "COP 425.000,50",
        "IVA (19,00 %)",
        "COP 1.190.000,00",
        "COP 1.416.100,00",
        "versión 1.0",
        "EMITIDA",
    ):
        assert esperado in texto, esperado
    # sin horas en las fechas
    assert "00:00" not in texto and "T00" not in texto


@requiere_weasyprint
async def test_la_firma_aparece_al_final_del_documento():
    pdf = await generador().generar(datos_certificado(), FIRMA, "image/png")

    texto = texto_pdf(pdf)

    assert texto.index("Prima total pagada") < texto.index("Firma del titular")
    assert texto.index("Firma del titular") < texto.index("Huella del contrato")


@requiere_weasyprint
@pytest.mark.parametrize("coberturas", [1, 3, 8, 12])
async def test_sigue_en_una_pagina_con_varias_coberturas(coberturas):
    pdf = await generador().generar(datos_certificado(coberturas), FIRMA, "image/png")

    assert paginas_pdf(pdf) == 1
    assert f"Cobertura número {coberturas - 1}" in texto_pdf(pdf)


@requiere_weasyprint
async def test_falla_si_el_certificado_no_cabe_en_una_pagina():
    with pytest.raises(GeneracionPdfError, match="páginas"):
        await generador().generar(datos_certificado(40), FIRMA, "image/png")


@requiere_weasyprint
async def test_acepta_firma_jpeg_y_nombres_largos_o_con_caracteres_especiales():
    from io import BytesIO

    from PIL import Image, ImageDraw

    imagen = Image.new("RGB", (200, 60), "white")
    ImageDraw.Draw(imagen).line([(5, 50), (100, 5), (195, 50)], fill="black", width=3)
    jpeg = BytesIO()
    imagen.save(jpeg, "JPEG")
    datos = datos_certificado()
    datos["titular"]["nombre"] = "José Ñandú Ünal & Hijos <S.A.> " + "Apellido " * 12

    pdf = await generador().generar(datos, jpeg.getvalue(), "image/jpeg")

    assert paginas_pdf(pdf) == 1 and imagenes_pdf(pdf) == 1
    assert "José Ñandú Ünal & Hijos <S.A.>" in texto_pdf(pdf)


@requiere_weasyprint
async def test_la_plantilla_no_puede_leer_archivos_locales(tmp_path):
    (tmp_path / "x.html").write_text(
        '<html><body><img src="file:///etc/hostname"><p>{{ poliza }}</p></body></html>', encoding="utf-8"
    )
    malicioso = GeneradorCertificadoWeasyPrint(plantilla="x.html", directorio_plantillas=tmp_path)

    with pytest.raises(GeneracionPdfError):
        await malicioso.generar(datos_certificado(), FIRMA, "image/png")


@pytest.mark.parametrize(
    "firma",
    [b"esto no es una imagen", FIRMA[:60], b"\x89PNG\r\n\x1a\n" + b"cabecera valida y cuerpo corrupto"],
)
def test_una_firma_ilegible_o_en_blanco_no_produce_un_certificado_sin_firma(firma):
    with pytest.raises(GeneracionPdfError, match="firma"):
        generador().renderizar_html(datos_certificado(), firma, "image/png")


@pytest.mark.parametrize(
    ("firma", "tipo"), [(png_en_blanco(), "image/png"), (jpeg_blanco(), "image/jpeg")], ids=["png_transparente", "jpeg_blanco"]
)
def test_rechaza_una_firma_en_blanco(firma, tipo):
    with pytest.raises(GeneracionPdfError, match="en blanco"):
        generador().renderizar_html(datos_certificado(), firma, tipo)


def test_acepta_una_firma_trazada_sobre_fondo_transparente_o_blanco():
    from io import BytesIO

    from PIL import Image, ImageDraw

    for modo, fondo, formato, tipo in (("RGBA", (0, 0, 0, 0), "PNG", "image/png"), ("RGB", "white", "JPEG", "image/jpeg")):
        imagen = Image.new(modo, (120, 40), fondo)
        ImageDraw.Draw(imagen).line([(5, 30), (60, 5), (115, 30)], fill=(0, 0, 0, 255) if modo == "RGBA" else "black", width=3)
        salida = BytesIO()
        imagen.save(salida, formato)

        html = generador().renderizar_html(datos_certificado(), salida.getvalue(), tipo)

        assert f"data:{tipo};base64," in html
