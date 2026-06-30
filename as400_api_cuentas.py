def _primer_valor(registro, *claves):
    for clave in claves:
        valor = registro.get(clave)

        if valor is not None and str(valor).strip() != "":
            return valor

    return ""


def _normalizar_codigo_cuenta(valor):
    texto = str(valor or "").strip()

    if not texto:
        return ""

    if texto.isdigit():
        return texto.zfill(10)

    return texto


def normalizar_registro_cuenta(cuenta):
    registro = dict(cuenta)
    codigo = _normalizar_codigo_cuenta(
        _primer_valor(registro, "codigo", "cuenta", "AICTA", "MCCTA")
    )
    nombre = str(
        _primer_valor(registro, "nombre", "titulo", "descripcion", "AINBR", "MCNBR")
    ).strip()
    tipo = _primer_valor(
        registro,
        "tipo",
        "tipo_cuenta",
        "tipocuenta",
        "MCTIPO",
        "MCTIP",
        "clase",
    )
    iva = _primer_valor(
        registro,
        "iva_porcentaje",
        "iva",
        "AIPIVA",
        "MCIVA",
        "porcentaje_iva",
    )
    activa = (
        registro.get("activa")
        if registro.get("activa") is not None
        else registro.get("MCACTIVA")
    )
    tercero_codigo = _primer_valor(
        registro,
        "tercero_codigo",
        "tercero",
        "MCTERCERO",
        "codigo_tercero",
    )
    tercero_nombre = _primer_valor(
        registro,
        "tercero_nombre",
        "MCTERCNOM",
        "nombre_tercero",
    )
    grupo_pgc = _primer_valor(registro, "grupo_pgc", "grupo", "MCGRUPO")
    subtipo = _primer_valor(registro, "subtipo", "MCSUBTIPO")
    naturaleza_cp = _primer_valor(registro, "naturaleza_cp", "AIPRE")
    masa_pyg = str(_primer_valor(registro, "masa_pyg", "AIDMPE")).strip()
    masa_balance = str(_primer_valor(registro, "masa_balance", "AIDMPP")).strip()
    es_base_iva = _primer_valor(registro, "es_base_iva", "AIBIVA")
    es_cuota_iva = _primer_valor(registro, "es_cuota_iva", "AICIVA")
    es_total_factura = _primer_valor(registro, "es_total_factura", "AITIVA")
    debe_haber_habitual = _primer_valor(
        registro,
        "debe_haber_habitual",
        "AIDOH",
    )
    palabras_clave = str(_primer_valor(registro, "palabras_clave", "AICLV")).strip()

    normalizada = {
        "codigo": codigo,
        "nombre": nombre,
    }
    opcionales = {
        "tipo": str(tipo).strip() or None,
        "iva_porcentaje": iva if iva != "" else None,
        "activa": activa,
        "tercero": str(tercero_codigo).strip() or None,
        "tercero_nombre": str(tercero_nombre).strip() or None,
        "grupo_pgc": str(grupo_pgc).strip() or None,
        "subtipo": str(subtipo).strip() or None,
        "naturaleza_cp": str(naturaleza_cp).strip() or None,
        "masa_pyg": masa_pyg or None,
        "masa_balance": masa_balance or None,
        "es_base_iva": es_base_iva if es_base_iva != "" else None,
        "es_cuota_iva": es_cuota_iva if es_cuota_iva != "" else None,
        "es_total_factura": es_total_factura if es_total_factura != "" else None,
        "debe_haber_habitual": str(debe_haber_habitual).strip() or None,
        "palabras_clave": palabras_clave or None,
    }

    for clave, valor in opcionales.items():
        if valor is not None and valor != "":
            normalizada[clave] = valor

    return normalizada
