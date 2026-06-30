import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import fcntl

from config import Config


ESTADO_PROCESANDO = "procesando"
ESTADO_OK = "ok"
ESTADO_ERROR = "error"


class HistorialError(Exception):
    pass


def historial_file_path():
    return Path(Config.APP_HISTORIAL_FILE)


def _lock_file_path():
    path = historial_file_path()
    return path.with_name(f"{path.name}.lock")


def _read_data_unlocked():
    path = historial_file_path()

    if not path.is_file():
        return {"operaciones": []}

    with path.open(encoding="utf-8") as fichero:
        data = json.load(fichero)

    if not isinstance(data, dict):
        raise HistorialError("El fichero de historial debe ser un objeto JSON")

    operaciones = data.get("operaciones", [])

    if not isinstance(operaciones, list):
        raise HistorialError("El campo operaciones debe ser una lista")

    return {"operaciones": operaciones}


def _write_data_unlocked(data):
    path = historial_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_name(f"{path.name}.tmp")

    with temporal.open("w", encoding="utf-8") as fichero:
        json.dump(data, fichero, ensure_ascii=False, indent=2)
        fichero.write("\n")

    os.replace(temporal, path)


@contextmanager
def _locked_data():
    path = historial_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_file_path()

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        data = _read_data_unlocked()

        try:
            yield data
            _write_data_unlocked(data)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def ahora_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalizar_idempotency_key(valor):
    texto = str(valor or "").strip()
    return texto[:160]


def nueva_idempotency_key():
    return uuid.uuid4().hex


def fingerprint_payload(payload):
    texto = json.dumps(
        payload or {},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _empresa_resumen(empresa):
    if not empresa:
        return {"id": "", "nombre": ""}

    empresa_id = str(empresa.get("id", "")).strip()
    return {
        "id": empresa_id,
        "nombre": empresa.get("nombre") or empresa_id,
    }


def crear_o_recuperar_operacion(
    *,
    tipo,
    idempotency_key,
    usuario,
    empresa,
    payload,
    lineas=None,
    proveedor_codigo="",
    proveedor_nombre="",
    fecha_operacion="",
    origen_reintento_id=None,
):
    tipo = str(tipo or "").strip().lower()

    if tipo not in {"pedido", "asiento"}:
        raise HistorialError("Tipo de operación no válido")

    idempotency_key = normalizar_idempotency_key(idempotency_key)
    payload_hash = fingerprint_payload(payload)
    empresa_info = _empresa_resumen(empresa)
    ahora = ahora_iso()

    with _locked_data() as data:
        if idempotency_key:
            for operacion in data["operaciones"]:
                if (
                    operacion.get("tipo") == tipo
                    and operacion.get("idempotency_key") == idempotency_key
                ):
                    if operacion.get("payload_fingerprint") != payload_hash:
                        return "conflicto", dict(operacion)

                    return "existente", dict(operacion)

        operacion = {
            "id": uuid.uuid4().hex,
            "tipo": tipo,
            "estado": ESTADO_PROCESANDO,
            "idempotency_key": idempotency_key,
            "payload_fingerprint": payload_hash,
            "usuario": str(usuario or ""),
            "empresa_id": empresa_info["id"],
            "empresa_nombre": empresa_info["nombre"],
            "proveedor_codigo": str(proveedor_codigo or "").strip(),
            "proveedor_nombre": str(proveedor_nombre or "").strip(),
            "fecha_operacion": str(fecha_operacion or "").strip(),
            "fecha_creacion": ahora,
            "fecha_actualizacion": ahora,
            "numero": "",
            "mensaje": "Operación en proceso",
            "error": "",
            "lineas": list(lineas or []),
            "payload": payload or {},
            "resultado": None,
            "http_status": None,
            "origen_reintento_id": origen_reintento_id,
        }
        data["operaciones"].append(operacion)

    return "creada", dict(operacion)


def completar_operacion(
    operacion_id,
    *,
    estado,
    resultado=None,
    http_status=None,
    numero="",
    mensaje="",
    error="",
):
    estado = str(estado or "").strip().lower()

    if estado not in {ESTADO_OK, ESTADO_ERROR}:
        raise HistorialError("Estado de operación no válido")

    with _locked_data() as data:
        for operacion in data["operaciones"]:
            if operacion.get("id") != operacion_id:
                continue

            operacion["estado"] = estado
            operacion["fecha_actualizacion"] = ahora_iso()
            operacion["resultado"] = resultado
            operacion["http_status"] = http_status
            operacion["numero"] = str(numero or "")
            operacion["mensaje"] = str(mensaje or "")
            operacion["error"] = str(error or "")
            return dict(operacion)

    raise HistorialError("Operación no encontrada")


def list_operaciones():
    with _locked_data() as data:
        operaciones = [dict(operacion) for operacion in data["operaciones"]]

    return sorted(
        operaciones,
        key=lambda item: item.get("fecha_creacion") or "",
        reverse=True,
    )


def get_operacion(operacion_id):
    operacion_id = str(operacion_id or "").strip()

    if not operacion_id:
        return None

    with _locked_data() as data:
        for operacion in data["operaciones"]:
            if operacion.get("id") == operacion_id:
                return dict(operacion)

    return None
