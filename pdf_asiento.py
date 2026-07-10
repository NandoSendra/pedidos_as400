import io
import re
from pathlib import Path

from ai_asiento import TIPOS_ASIENTO_POR_ID, _parsear_importe_locale, _texto_para_analisis


class PDFAsientoError(Exception):
    pass


EXTENSIONES_PDF = {".pdf"}
MAX_TEXTO_PDF_IA = 12000


def es_fichero_pdf(filename):
    return Path(str(filename or "")).suffix.lower() in EXTENSIONES_PDF


def _celda_importe(coincidencia):
    if not coincidencia:
        return None

    return _parsear_importe_locale(coincidencia.group(1))


def extraer_texto_pdf(contenido):
    if not contenido:
        raise PDFAsientoError("El PDF está vacío")

    errores = []

    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError as error:
            raise PDFAsientoError(
                "Instala la dependencia pypdf para leer facturas PDF"
            ) from error

    try:
        lector = PdfReader(io.BytesIO(contenido))
        paginas = []

        for indice, pagina in enumerate(lector.pages, start=1):
            texto = pagina.extract_text() or ""
            texto = texto.strip()

            if texto:
                paginas.append(f"--- Página {indice} ---\n{texto}")

        if paginas:
            return "\n\n".join(paginas), len(lector.pages)
    except Exception as error:
        errores.append(f"pypdf: {error}")

    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber is not None:
        try:
            paginas = []

            with pdfplumber.open(io.BytesIO(contenido)) as documento:
                for indice, pagina in enumerate(documento.pages, start=1):
                    texto = pagina.extract_text() or ""
                    texto = texto.strip()

                    if texto:
                        paginas.append(f"--- Página {indice} ---\n{texto}")

                if paginas:
                    return "\n\n".join(paginas), len(documento.pages)
        except Exception as error:
            errores.append(f"pdfplumber: {error}")

    detalle = "; ".join(errores) if errores else "sin texto legible"

    raise PDFAsientoError(
        "No se pudo extraer texto del PDF. "
        "Si es un escaneo, prueba con un PDF con texto seleccionable o "
        "describe la operación en el cuadro de la IA. "
        f"Detalle: {detalle}"
    )


def _buscar_importe(texto, patrones):
    for patron in patrones:
        coincidencia = re.search(patron, texto, re.IGNORECASE)

        if coincidencia:
            importe = _celda_importe(coincidencia)

            if importe is not None and importe > 0:
                return importe

    return None


def extraer_datos_factura(texto):
    texto_busqueda = _texto_para_analisis(texto)
    datos = {}

    tipo_iva = re.search(
        r"\biva\s*(?:del?\s*)?(\d{1,2}(?:[.,]\d+)?)\s*%",
        texto_busqueda,
    )

    if tipo_iva:
        try:
            datos["tipo_iva"] = int(round(float(tipo_iva.group(1).replace(",", "."))))
        except (TypeError, ValueError):
            pass

    datos["base_imponible"] = _buscar_importe(
        texto_busqueda,
        (
            r"base\s+imponible[^\d]{0,20}([\d.,]+)",
            r"base\s+imp[^\d]{0,20}([\d.,]+)",
            r"subtotal[^\d]{0,20}([\d.,]+)",
        ),
    )
    datos["cuota_iva"] = _buscar_importe(
        texto_busqueda,
        (
            r"cuota\s+iva[^\d]{0,20}([\d.,]+)",
            r"importe\s+iva[^\d]{0,20}([\d.,]+)",
            r"\biva\s*\d{1,2}\s*%[^\d]{0,20}([\d.,]+)",
        ),
    )
    datos["total"] = _buscar_importe(
        texto_busqueda,
        (
            r"total\s+factura[^\d]{0,20}([\d.,]+)",
            r"importe\s+total[^\d]{0,20}([\d.,]+)",
            r"total\s+a\s+pagar[^\d]{0,20}([\d.,]+)",
            r"total[^\d]{0,12}([\d.,]+)\s*€",
        ),
    )

    numero = re.search(
        r"(?:factura|fatura|invoice|n[ºo°.]?\s*fac\.?)"
        r"[^\d]{0,12}(\d[\d./-]{2,})",
        texto_busqueda,
        re.IGNORECASE,
    )

    if numero:
        datos["numero_factura"] = numero.group(1).strip()

    fecha = re.search(
        r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b",
        texto_busqueda,
    )

    if fecha:
        datos["fecha_documento"] = fecha.group(1)

    emisor = re.search(
        r"(?:proveedor|emisor|vendedor|supplier)\s*[:\-]?\s*(.+)",
        texto,
        re.IGNORECASE,
    )
    receptor = re.search(
        r"(?:cliente|receptor|buyer|destinatario)\s*[:\-]?\s*(.+)",
        texto,
        re.IGNORECASE,
    )

    if emisor:
        datos["emisor"] = emisor.group(1).split("\n")[0].strip()[:80]

    if receptor:
        datos["receptor"] = receptor.group(1).split("\n")[0].strip()[:80]

    return {clave: valor for clave, valor in datos.items() if valor not in (None, "")}


def inferir_tipo_documento(texto, tipo_usuario=None):
    tipo_usuario = str(tipo_usuario or "").strip()

    if tipo_usuario in TIPOS_ASIENTO_POR_ID:
        return tipo_usuario

    texto_norm = _texto_para_analisis(texto)

    puntuaciones = {
        "factura_venta": 0,
        "factura_compra": 0,
        "gasto": 0,
        "cobro": 0,
        "pago": 0,
    }

    if any(palabra in texto_norm for palabra in ("factura emitida", "factura de venta", "factura venta")):
        puntuaciones["factura_venta"] += 4

    if any(palabra in texto_norm for palabra in ("factura recibida", "factura de compra", "factura compra")):
        puntuaciones["factura_compra"] += 4

    if "iva repercutido" in texto_norm or "repercutido" in texto_norm:
        puntuaciones["factura_venta"] += 3

    if "iva soportado" in texto_norm or "soportado" in texto_norm:
        puntuaciones["factura_compra"] += 3

    if any(palabra in texto_norm for palabra in ("ticket", "justificante", "recibo", "talon")):
        puntuaciones["gasto"] += 3

    if any(palabra in texto_norm for palabra in ("cobro", "ingreso", "abono en cuenta")):
        puntuaciones["cobro"] += 2

    if any(palabra in texto_norm for palabra in ("pago", "transferencia", "domiciliacion")):
        puntuaciones["pago"] += 2

    if "cliente" in texto_norm:
        puntuaciones["factura_venta"] += 1

    if any(palabra in texto_norm for palabra in ("proveedor", "acreedor", "compra")):
        puntuaciones["factura_compra"] += 1

    mejor_tipo, mejor_puntuacion = max(puntuaciones.items(), key=lambda item: item[1])

    if mejor_puntuacion >= 2:
        return mejor_tipo

    return None


def _etiqueta_tipo(tipo_id):
    tipo = TIPOS_ASIENTO_POR_ID.get(tipo_id)
    return tipo["etiqueta"] if tipo else "Documento"


def construir_resumen_pdf(
    texto,
    datos,
    tipo_documento=None,
    descripcion_extra="",
    num_paginas=1,
    nombre_archivo="",
):
    lineas = ["DOCUMENTO PDF PARA CONTABILIZAR"]

    if nombre_archivo:
        lineas.append(f"Archivo: {nombre_archivo}")

    lineas.append(f"Páginas leídas: {num_paginas}")

    if tipo_documento:
        lineas.append(f"Tipo de operación: {_etiqueta_tipo(tipo_documento)}")

    if descripcion_extra:
        lineas.append(f"Indicaciones del usuario: {descripcion_extra}")

    if datos:
        lineas.append("Datos detectados en el documento:")

        if datos.get("numero_factura"):
            lineas.append(f"- Número factura: {datos['numero_factura']}")

        if datos.get("fecha_documento"):
            lineas.append(f"- Fecha documento: {datos['fecha_documento']}")

        if datos.get("emisor"):
            lineas.append(f"- Emisor/proveedor: {datos['emisor']}")

        if datos.get("receptor"):
            lineas.append(f"- Cliente/receptor: {datos['receptor']}")

        if datos.get("base_imponible") is not None:
            lineas.append(f"- Base imponible: {datos['base_imponible']:.2f} €")

        if datos.get("tipo_iva") is not None:
            lineas.append(f"- Tipo IVA: {datos['tipo_iva']}%")

        if datos.get("cuota_iva") is not None:
            lineas.append(f"- Cuota IVA: {datos['cuota_iva']:.2f} €")

        if datos.get("total") is not None:
            lineas.append(f"- Total: {datos['total']:.2f} €")

    if tipo_documento in {"factura_compra", "factura_venta"} and datos.get("base_imponible"):
        tipo_iva = datos.get("tipo_iva") or 21
        lineas.append(
            f"Propón asiento de {_etiqueta_tipo(tipo_documento).lower()} "
            f"con base {datos['base_imponible']:.2f} € + IVA {tipo_iva}%."
        )
    elif tipo_documento:
        lineas.append(
            f"Propón el asiento contable más adecuado para un documento de tipo "
            f"{_etiqueta_tipo(tipo_documento)}."
        )
    else:
        lineas.append(
            "Analiza el documento e identifica si es factura de compra, factura de venta, "
            "ticket/gasto, cobro, pago u otra operación, y propón el asiento cuadrado."
        )

    texto_recortado = texto[:MAX_TEXTO_PDF_IA]

    if len(texto) > MAX_TEXTO_PDF_IA:
        lineas.append(
            f"(Texto del PDF recortado a {MAX_TEXTO_PDF_IA} caracteres para el análisis.)"
        )

    lineas.append("")
    lineas.append("TEXTO EXTRAÍDO DEL PDF:")
    lineas.append(texto_recortado)

    return "\n".join(lineas).strip()


def parsear_pdf_para_ia(
    contenido,
    filename=None,
    tipo_asiento=None,
    descripcion_extra="",
):
    texto, num_paginas = extraer_texto_pdf(contenido)
    datos = extraer_datos_factura(texto)
    tipo_documento = inferir_tipo_documento(texto, tipo_usuario=tipo_asiento)
    resumen = construir_resumen_pdf(
        texto,
        datos,
        tipo_documento=tipo_documento,
        descripcion_extra=descripcion_extra,
        num_paginas=num_paginas,
        nombre_archivo=filename or "",
    )

    return {
        "formato": "pdf",
        "modo": "ia",
        "num_filas": 0,
        "encabezados": [],
        "delimitador": None,
        "resumen": resumen,
        "texto_extraido": texto,
        "tipo_sugerido": tipo_documento,
        "datos_documento": datos,
        "num_paginas": num_paginas,
        "diagnostico": {
            "formato": "pdf",
            "num_paginas": num_paginas,
            "caracteres_extraidos": len(texto),
            "tipo_sugerido": tipo_documento,
            "datos_detectados": datos,
            "filas_validas": 0,
            "filas_descartadas": 0,
            "errores": [],
            "cuentas_no_encontradas": [],
        },
    }
