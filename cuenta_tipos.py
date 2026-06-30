import re
import unicodedata


ETIQUETAS_TIPO = {
    "cliente": "Cliente",
    "proveedor": "Proveedor",
    "iva_repercutido": "IVA repercutido",
    "iva_soportado": "IVA soportado",
    "iva_repercutido_especial": "IVA repercutido (intracom./especial)",
    "iva_soportado_especial": "IVA soportado (intracom./especial)",
    "ventas": "Ventas / ingresos",
    "compra_gasto": "Compras / gastos",
    "servicios": "Servicios exteriores",
    "otros_gastos": "Otros gastos",
    "banco": "Banco / tesorería",
    "caja": "Caja / efectivo",
    "gastos_personal": "Gastos de personal",
    "ss_empresa": "Seg. Social empresa",
    "empleado": "Empleado / nómina",
    "irpf": "IRPF retenciones",
    "ss_acreedora": "Seg. Social acreedora",
    "deuda_financiera": "Deuda financiera",
    "capital": "Capital / reservas",
    "otros": "Otros",
}

TIPOS_POR_PREFIJO = {
    "430": "cliente",
    "431": "cliente",
    "432": "cliente",
    "433": "cliente",
    "434": "cliente",
    "435": "cliente",
    "436": "cliente",
    "437": "cliente",
    "400": "proveedor",
    "401": "proveedor",
    "410": "proveedor",
    "411": "proveedor",
    "700": "ventas",
    "701": "ventas",
    "705": "ventas",
    "706": "ventas",
    "708": "ventas",
    "709": "ventas",
    "740": "ventas",
    "600": "compra_gasto",
    "601": "compra_gasto",
    "602": "compra_gasto",
    "607": "compra_gasto",
    "608": "compra_gasto",
    "609": "compra_gasto",
    "621": "servicios",
    "622": "servicios",
    "623": "servicios",
    "624": "servicios",
    "625": "servicios",
    "626": "servicios",
    "627": "servicios",
    "628": "servicios",
    "629": "otros_gastos",
    "572": "banco",
    "573": "banco",
    "574": "banco",
    "575": "banco",
    "576": "banco",
    "570": "caja",
    "571": "caja",
    "640": "gastos_personal",
    "642": "ss_empresa",
    "465": "empleado",
    "475": "irpf",
    "476": "ss_acreedora",
    "520": "deuda_financiera",
    "521": "deuda_financiera",
    "100": "capital",
    "112": "capital",
    "113": "capital",
    "114": "capital",
}

ALIAS_TIPO_EXTERNO = {
    "cliente": "cliente",
    "clientes": "cliente",
    "c": "cliente",
    "proveedor": "proveedor",
    "proveedores": "proveedor",
    "acreedor": "proveedor",
    "p": "proveedor",
    "iva repercutido": "iva_repercutido",
    "iva_repercutido": "iva_repercutido",
    "repercutido": "iva_repercutido",
    "iva soportado": "iva_soportado",
    "iva_soportado": "iva_soportado",
    "soportado": "iva_soportado",
    "ventas": "ventas",
    "ingresos": "ventas",
    "banco": "banco",
    "tesoreria": "banco",
    "caja": "caja",
    "gasto": "compra_gasto",
    "gastos": "compra_gasto",
    "compra": "compra_gasto",
    "compras": "compra_gasto",
    "nomina": "empleado",
    "nominas": "empleado",
    "empleado": "empleado",
    "personal": "gastos_personal",
}

NOMBRES_GENERICOS = (
    "cliente contado",
    "proveedor contado",
    "cliente interno",
    "proveedor interno",
    "clientes varios",
    "proveedores varios",
    "acreedor contado",
    "acreedores varios",
)


def _normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(
        caracter for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return texto.lower().strip()


def etiqueta_tipo_cuenta(tipo):
    return ETIQUETAS_TIPO.get(tipo, tipo or "Otros")


def normalizar_tipo_externo(valor):
    if not valor:
        return None

    clave = _normalizar_texto(valor)
    clave = re.sub(r"[^a-z0-9_ ]", "", clave)

    return ALIAS_TIPO_EXTERNO.get(clave, clave.replace(" ", "_"))


def normalizar_activa(valor):
    if valor is None or valor == "":
        return None

    if isinstance(valor, bool):
        return valor

    texto = str(valor).strip().upper()

    if texto in {"S", "SI", "Y", "YES", "1", "TRUE", "A", "ACTIVA"}:
        return True

    if texto in {"N", "NO", "0", "FALSE", "B", "BAJA", "INACTIVA"}:
        return False

    return None


def normalizar_iva_porcentaje(valor):
    if valor is None or valor == "":
        return None

    try:
        porcentaje = float(str(valor).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None

    if porcentaje <= 0:
        return None

    return int(round(porcentaje)) if 0 < porcentaje <= 100 else None


def es_flag_si(valor):
    return str(valor or "").strip().upper() in {"S", "SI", "Y", "1", "TRUE"}


def normalizar_naturaleza_cp(valor):
    texto = str(valor or "").strip().upper()

    if texto == "C":
        return "cliente"

    if texto == "P":
        return "proveedor"

    return None


def normalizar_debe_haber_habitual(valor):
    texto = str(valor or "").strip().upper()

    if texto in {"D", "DEBE"}:
        return "D"

    if texto in {"H", "HABER"}:
        return "H"

    return None


def inferir_rol_factura(cuenta):
    if cuenta.get("rol_factura"):
        return cuenta["rol_factura"]

    if es_flag_si(cuenta.get("es_base_iva")):
        return "base"

    if es_flag_si(cuenta.get("es_cuota_iva")):
        return "cuota_iva"

    if es_flag_si(cuenta.get("es_total_factura")):
        return "total"

    return None


def inferir_tipo_desde_masas(masa_pyg="", masa_balance=""):
    texto = _normalizar_texto(f"{masa_pyg} {masa_balance}")

    if "cliente" in texto:
        return "cliente"

    if "proveedor" in texto:
        return "proveedor"

    if "venta" in texto or "ingreso" in texto:
        return "ventas"

    if "administracion" in texto or "iva" in texto:
        return None

    if "banco" in texto or "tesorer" in texto:
        return "banco"

    if "personal" in texto or "nomina" in texto:
        return "gastos_personal"

    return None


def inferir_tipo_cuenta(codigo, nombre="", cuenta=None):
    cuenta = cuenta or {}
    codigo = str(codigo or "").strip()
    nombre_norm = _normalizar_texto(nombre)
    prefijo = codigo[:3] if len(codigo) >= 3 else codigo

    naturaleza = normalizar_naturaleza_cp(cuenta.get("naturaleza_cp"))

    if naturaleza:
        return naturaleza

    tipo_masa = inferir_tipo_desde_masas(
        cuenta.get("masa_pyg", ""),
        cuenta.get("masa_balance", ""),
    )

    if tipo_masa:
        return tipo_masa

    rol = inferir_rol_factura(cuenta)

    if rol == "cuota_iva":
        if prefijo.startswith("477") or "repercut" in nombre_norm:
            return "iva_repercutido_especial" if any(
                termino in nombre_norm
                for termino in ("intrac", "tercer", "invers", "3o", "3º", "pasivo")
            ) else "iva_repercutido"

        if prefijo.startswith("472") or "soport" in nombre_norm:
            return "iva_soportado_especial" if any(
                termino in nombre_norm
                for termino in ("intrac", "tercer", "invers", "3o", "3º", "pasivo")
            ) else "iva_soportado"

    if prefijo == "477" or (
        codigo.startswith("477") and "repercut" in nombre_norm
    ):
        if any(
            termino in nombre_norm
            for termino in ("intrac", "tercer", "invers", "3o", "3º", "pasivo")
        ):
            return "iva_repercutido_especial"
        return "iva_repercutido"

    if prefijo == "472" or (
        codigo.startswith("472") and "soport" in nombre_norm
    ):
        if any(
            termino in nombre_norm
            for termino in ("intrac", "tercer", "invers", "3o", "3º", "pasivo")
        ):
            return "iva_soportado_especial"
        return "iva_soportado"

    if prefijo in TIPOS_POR_PREFIJO:
        return TIPOS_POR_PREFIJO[prefijo]

    if "cliente" in nombre_norm and prefijo.startswith("43"):
        return "cliente"

    if any(
        termino in nombre_norm
        for termino in ("proveedor", "acreedor", "acreedora")
    ) and prefijo.startswith("4"):
        return "proveedor"

    if "venta" in nombre_norm and prefijo.startswith("7"):
        return "ventas"

    if any(
        termino in nombre_norm
        for termino in ("banco", "bbva", "santander", "caixa", "sabadell")
    ):
        return "banco"

    return "otros"


def inferir_iva_porcentaje(codigo, nombre="", tipo=None):
    codigo = str(codigo or "").strip()
    nombre_norm = _normalizar_texto(nombre)

    coincidencia = re.match(r"^(477|472)00000(\d{2})$", codigo)

    if coincidencia:
        return int(coincidencia.group(2))

    coincidencia = re.search(r"(\d{1,2})\s*%", nombre_norm)

    if coincidencia:
        return int(coincidencia.group(1))

    if tipo in {"iva_repercutido", "iva_soportado"}:
        coincidencia = re.search(r"\b(\d{1,2})\b", codigo[-4:])

        if coincidencia:
            porcentaje = int(coincidencia.group(1))

            if 0 < porcentaje <= 30:
                return porcentaje

    return None


def inferir_grupo_pgc(codigo):
    codigo = str(codigo or "").strip()

    if len(codigo) >= 3:
        return codigo[:3]

    if len(codigo) >= 2:
        return codigo[:2]

    return codigo


def es_cuenta_generica(nombre):
    nombre_norm = _normalizar_texto(nombre)

    return any(termino in nombre_norm for termino in NOMBRES_GENERICOS)


def inferir_tercero_nombre(codigo, nombre, tipo, tercero_externo=None):
    if tercero_externo:
        return str(tercero_externo).strip()

    if tipo not in {"cliente", "proveedor", "empleado"}:
        return None

    nombre_limpio = str(nombre or "").strip()

    if not nombre_limpio or es_cuenta_generica(nombre_limpio):
        return None

    return nombre_limpio


def inferir_subtipo(codigo, nombre, tipo):
    nombre_norm = _normalizar_texto(nombre)

    if tipo in {"iva_repercutido_especial", "iva_soportado_especial"}:
        if "intrac" in nombre_norm:
            return "intracomunitario"
        if "invers" in nombre_norm or "pasivo" in nombre_norm:
            return "inversion_sujeto_pasivo"
        return "especial"

    if tipo in {"iva_repercutido", "iva_soportado"}:
        return "normal"

    if es_cuenta_generica(nombre):
        return "generica"

    if tipo in {"cliente", "proveedor"}:
        return "tercero"

    return None


def enriquecer_cuenta(cuenta):
    cuenta = dict(cuenta)
    codigo = str(cuenta.get("codigo", "")).strip()
    nombre = cuenta.get("nombre", "")

    if es_flag_si(cuenta.get("es_base_iva")):
        cuenta["rol_factura"] = "base"
    elif es_flag_si(cuenta.get("es_cuota_iva")):
        cuenta["rol_factura"] = "cuota_iva"
    elif es_flag_si(cuenta.get("es_total_factura")):
        cuenta["rol_factura"] = "total"

    tipo = normalizar_tipo_externo(cuenta.get("tipo"))

    if not tipo:
        tipo_naturaleza = normalizar_naturaleza_cp(cuenta.get("naturaleza_cp"))

        if tipo_naturaleza:
            tipo = tipo_naturaleza

    if not tipo:
        tipo = inferir_tipo_cuenta(codigo, nombre, cuenta)

    iva_porcentaje = normalizar_iva_porcentaje(
        cuenta.get("iva_porcentaje") or cuenta.get("iva")
    )

    if iva_porcentaje is None:
        iva_porcentaje = inferir_iva_porcentaje(codigo, nombre, tipo)

    activa = normalizar_activa(cuenta.get("activa"))

    if activa is None:
        activa = True

    tercero = inferir_tercero_nombre(
        codigo,
        nombre,
        tipo,
        cuenta.get("tercero_nombre") or cuenta.get("tercero"),
    )

    debe_haber_habitual = normalizar_debe_haber_habitual(
        cuenta.get("debe_haber_habitual")
    )

    cuenta["tipo"] = tipo
    cuenta["tipo_etiqueta"] = etiqueta_tipo_cuenta(tipo)
    cuenta["iva_porcentaje"] = iva_porcentaje
    cuenta["activa"] = activa
    cuenta["grupo_pgc"] = cuenta.get("grupo_pgc") or inferir_grupo_pgc(codigo)
    cuenta["generica"] = bool(cuenta.get("generica")) or es_cuenta_generica(nombre)
    cuenta["subtipo"] = cuenta.get("subtipo") or inferir_subtipo(codigo, nombre, tipo)
    cuenta["rol_factura"] = inferir_rol_factura(cuenta)

    if debe_haber_habitual:
        cuenta["debe_haber_habitual"] = debe_haber_habitual

    if tercero:
        cuenta["tercero_nombre"] = tercero

    return cuenta


def formatear_cuenta_para_ia(cuenta):
    partes = [
        str(cuenta.get("codigo", "")),
        str(cuenta.get("nombre", "")),
        etiqueta_tipo_cuenta(cuenta.get("tipo")),
    ]

    if cuenta.get("iva_porcentaje") is not None:
        partes.append(f"IVA {cuenta['iva_porcentaje']}%")

    if cuenta.get("rol_factura"):
        roles = {
            "base": "base imponible",
            "cuota_iva": "cuota IVA",
            "total": "total factura",
        }
        partes.append(roles.get(cuenta["rol_factura"], cuenta["rol_factura"]))

    if cuenta.get("debe_haber_habitual"):
        lado = "Debe" if cuenta["debe_haber_habitual"] == "D" else "Haber"
        partes.append(f"{lado} habitual")

    if cuenta.get("masa_pyg"):
        partes.append(f"PyG={cuenta['masa_pyg']}")

    if cuenta.get("masa_balance"):
        partes.append(f"Balance={cuenta['masa_balance']}")

    if cuenta.get("tercero_nombre"):
        partes.append(f"tercero={cuenta['tercero_nombre']}")

    if cuenta.get("palabras_clave"):
        partes.append(f"claves={cuenta['palabras_clave']}")

    if cuenta.get("subtipo") == "generica":
        partes.append("genérica")

    if cuenta.get("subtipo") in {"intracomunitario", "inversion_sujeto_pasivo", "especial"}:
        partes.append(cuenta["subtipo"].replace("_", " "))

    if cuenta.get("activa") is False:
        partes.append("INACTIVA")

    return "|".join(partes)


def tipos_cuenta_esperados(tipos_operacion):
    esperados = set()

    mapa = {
        "factura_venta": {
            "cliente", "ventas", "iva_repercutido",
        },
        "factura_compra": {
            "proveedor", "compra_gasto", "servicios", "otros_gastos", "iva_soportado",
        },
        "cobro": {"cliente", "banco", "caja"},
        "pago": {"proveedor", "empleado", "banco", "caja", "deuda_financiera"},
        "nomina": {
            "gastos_personal", "ss_empresa", "empleado", "irpf",
            "ss_acreedora", "banco",
        },
        "confirming": {"proveedor", "banco", "deuda_financiera"},
        "banco": {"banco", "caja"},
        "gasto": {"compra_gasto", "servicios", "otros_gastos", "banco"},
    }

    for tipo_operacion in tipos_operacion:
        esperados.update(mapa.get(tipo_operacion, set()))

    return esperados


def cuenta_utilizable_ia(cuenta):
    return cuenta.get("activa", True) is not False


def texto_busqueda_cuenta(cuenta):
    partes = [
        cuenta.get("nombre", ""),
        cuenta.get("tercero_nombre", ""),
        cuenta.get("palabras_clave", ""),
    ]

    return _normalizar_texto(" ".join(str(parte) for parte in partes if parte))


def puntuar_busqueda_cuenta(cuenta, tokens):
    if not tokens:
        return 0

    texto_completo = texto_busqueda_cuenta(cuenta)
    claves = _normalizar_texto(cuenta.get("palabras_clave", ""))
    palabras = [
        palabra for palabra in re.split(r"[^a-z0-9]+", texto_completo) if palabra
    ]
    puntuacion = 0

    for token in tokens:
        if not token or token.isdigit():
            continue

        if token in palabras:
            puntuacion += 12
        elif any(token in palabra for palabra in palabras):
            puntuacion += 6
        elif token in texto_completo:
            puntuacion += 2

        if claves:
            if token in claves:
                puntuacion += 10
            elif any(
                token in palabra
                for palabra in re.split(r"[^a-z0-9]+", claves)
                if palabra
            ):
                puntuacion += 5

    return puntuacion


def cuenta_coincide_busqueda(cuenta, busqueda):
    texto = _normalizar_texto(busqueda)

    if len(texto) < 2:
        return False

    codigo = _normalizar_texto(cuenta.get("codigo", ""))

    if texto in codigo:
        return True

    return texto in texto_busqueda_cuenta(cuenta)


def resolver_codigo_cuenta(valor, cuentas):
    texto = str(valor or "").strip()

    if not texto:
        return ""

    codigos_validos = {str(cuenta.get("codigo", "")).strip() for cuenta in cuentas}

    if texto in codigos_validos:
        return texto

    candidatos = []

    if "|" in texto:
        candidatos.append(texto.split("|", 1)[0].strip())

    coincidencia = re.match(r"^(\d+)", texto)

    if coincidencia:
        candidatos.append(coincidencia.group(1))

    for codigo in candidatos:
        if codigo in codigos_validos:
            return codigo

    return candidatos[0] if candidatos else texto
