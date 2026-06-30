import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import Config

MAX_EJEMPLOS_POR_EMPRESA = 200


class AsientosEjemplosError(Exception):
    pass


def ejemplos_file_path():
    return Path(Config.APP_ASIENTOS_EJEMPLOS_FILE)


def ejemplos_example_file_path():
    return ejemplos_file_path().with_name(
        f"{ejemplos_file_path().name}.example"
    )


def _asegurar_fichero_ejemplos():
    path = ejemplos_file_path()

    if path.is_file():
        return

    ejemplo = ejemplos_example_file_path()

    if ejemplo.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ejemplo.read_text(encoding="utf-8"), encoding="utf-8")


def _read_data():
    _asegurar_fichero_ejemplos()
    path = ejemplos_file_path()

    if not path.is_file():
        return {"ejemplos": []}

    with path.open(encoding="utf-8") as fichero:
        data = json.load(fichero)

    if not isinstance(data, dict):
        raise AsientosEjemplosError("El fichero de ejemplos debe ser un objeto JSON")

    ejemplos = data.get("ejemplos", [])

    if not isinstance(ejemplos, list):
        raise AsientosEjemplosError("El campo ejemplos debe ser una lista")

    return {"ejemplos": ejemplos}


def _write_data(data):
    path = ejemplos_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as fichero:
        json.dump(data, fichero, ensure_ascii=False, indent=2)


def _normalizar_empresa_id(empresa_id):
    return str(empresa_id or "default").strip() or "default"


def _normalizar_lineas_ejemplo(lineas):
    normalizadas = []

    for linea in lineas or []:
        cuenta = str(linea.get("cuenta", "")).strip()

        if not cuenta:
            continue

        try:
            importe = round(float(linea.get("importe", 0)), 2)
        except (TypeError, ValueError):
            continue

        if importe <= 0:
            continue

        debe_haber = str(linea.get("debe_haber", "")).strip().upper()

        if debe_haber not in {"D", "H"}:
            continue

        concepto = str(linea.get("concepto", "")).strip() or "Sin concepto"

        normalizadas.append({
            "cuenta": cuenta,
            "importe": importe,
            "debe_haber": debe_haber,
            "concepto": concepto,
        })

    return normalizadas


def _firma_ejemplo(descripcion, lineas):
    return json.dumps(
        {
            "descripcion": str(descripcion or "").strip().lower(),
            "lineas": lineas,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def list_ejemplos_por_empresa(empresa_id, incluir_inactivos=False):
    empresa_id = _normalizar_empresa_id(empresa_id)

    return [
        dict(ejemplo)
        for ejemplo in _read_data()["ejemplos"]
        if _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
        and (incluir_inactivos or ejemplo.get("activo", True) is not False)
    ]


def contar_ejemplos(empresa_id):
    return len(list_ejemplos_por_empresa(empresa_id))


def get_ejemplo(empresa_id, ejemplo_id):
    empresa_id = _normalizar_empresa_id(empresa_id)
    ejemplo_id = str(ejemplo_id or "").strip()

    for ejemplo in _read_data()["ejemplos"]:
        if (
            _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
            and ejemplo.get("id") == ejemplo_id
        ):
            return dict(ejemplo)

    return None


def guardar_ejemplo(
    empresa_id,
    descripcion,
    lineas,
    usuario=None,
    tipos_operacion=None,
):
    empresa_id = _normalizar_empresa_id(empresa_id)
    lineas = _normalizar_lineas_ejemplo(lineas)

    if len(lineas) < 2:
        raise AsientosEjemplosError(
            "El ejemplo debe tener al menos dos líneas con importe mayor que 0"
        )

    descripcion = str(descripcion or "").strip()

    if len(descripcion) < 5:
        descripcion = " | ".join(
            f"{linea['cuenta']} {linea['debe_haber']} {linea['importe']:.2f}"
            for linea in lineas[:4]
        )

    data = _read_data()
    firma = _firma_ejemplo(descripcion, lineas)
    ahora = datetime.now(timezone.utc).isoformat()

    for ejemplo in data["ejemplos"]:
        if (
            _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
            and _firma_ejemplo(ejemplo.get("descripcion"), ejemplo.get("lineas")) == firma
        ):
            ejemplo["actualizado"] = ahora
            ejemplo["descripcion"] = descripcion
            ejemplo["lineas"] = lineas
            ejemplo["tipos_operacion"] = list(tipos_operacion or [])
            ejemplo["usuario"] = usuario or ejemplo.get("usuario")
            ejemplo["activo"] = True
            _write_data(data)

            return dict(ejemplo)

    ejemplos_empresa = [
        ejemplo
        for ejemplo in data["ejemplos"]
        if _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
    ]

    if len(ejemplos_empresa) >= MAX_EJEMPLOS_POR_EMPRESA:
        mas_antiguo = min(
            ejemplos_empresa,
            key=lambda item: item.get("actualizado") or item.get("creado") or "",
        )
        data["ejemplos"] = [
            ejemplo
            for ejemplo in data["ejemplos"]
            if ejemplo.get("id") != mas_antiguo.get("id")
        ]

    nuevo = {
        "id": uuid.uuid4().hex,
        "empresa_id": empresa_id,
        "descripcion": descripcion,
        "lineas": lineas,
        "tipos_operacion": list(tipos_operacion or []),
        "usuario": usuario,
        "activo": True,
        "creado": ahora,
        "actualizado": ahora,
    }

    data["ejemplos"].append(nuevo)
    _write_data(data)

    return nuevo


def actualizar_ejemplo(
    empresa_id,
    ejemplo_id,
    *,
    descripcion=None,
    lineas=None,
    tipos_operacion=None,
    activo=None,
    usuario=None,
):
    empresa_id = _normalizar_empresa_id(empresa_id)
    ejemplo_id = str(ejemplo_id or "").strip()
    data = _read_data()
    ahora = datetime.now(timezone.utc).isoformat()

    for ejemplo in data["ejemplos"]:
        if (
            _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
            and ejemplo.get("id") == ejemplo_id
        ):
            if descripcion is not None:
                descripcion = str(descripcion or "").strip()

                if len(descripcion) < 5:
                    raise AsientosEjemplosError("La descripción debe tener al menos 5 caracteres")

                ejemplo["descripcion"] = descripcion

            if lineas is not None:
                normalizadas = _normalizar_lineas_ejemplo(lineas)

                if len(normalizadas) < 2:
                    raise AsientosEjemplosError(
                        "El ejemplo debe tener al menos dos líneas con importe mayor que 0"
                    )

                ejemplo["lineas"] = normalizadas

            if tipos_operacion is not None:
                ejemplo["tipos_operacion"] = [
                    str(tipo).strip()
                    for tipo in tipos_operacion
                    if str(tipo).strip()
                ]

            if activo is not None:
                ejemplo["activo"] = bool(activo)

            if usuario:
                ejemplo["usuario"] = usuario

            ejemplo["actualizado"] = ahora
            _write_data(data)
            return dict(ejemplo)

    raise AsientosEjemplosError("Ejemplo no encontrado")


def borrar_ejemplo(empresa_id, ejemplo_id):
    empresa_id = _normalizar_empresa_id(empresa_id)
    ejemplo_id = str(ejemplo_id or "").strip()
    data = _read_data()
    num_antes = len(data["ejemplos"])
    data["ejemplos"] = [
        ejemplo
        for ejemplo in data["ejemplos"]
        if not (
            _normalizar_empresa_id(ejemplo.get("empresa_id")) == empresa_id
            and ejemplo.get("id") == ejemplo_id
        )
    ]

    if len(data["ejemplos"]) == num_antes:
        raise AsientosEjemplosError("Ejemplo no encontrado")

    _write_data(data)
