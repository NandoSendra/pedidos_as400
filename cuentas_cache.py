import time
from datetime import datetime, timezone
from threading import Lock

from as400_api import obtener_cuentas
from cuenta_tipos import cuenta_coincide_busqueda
from plan_contable_ia import consolidar_cuentas_con_plan_ia, get_plan_contable_info

_lock = Lock()
_store = {}
TTL_SECONDS = 3600


def _clave_orden_cuenta(cuenta):
    return str(cuenta.get("codigo") or "")


def get_cuentas_contables(empresa, refresh=False):
    empresa_id = str(empresa.get("id") or "default")
    ahora = time.time()

    if not refresh:
        with _lock:
            entrada = _store.get(empresa_id)

            if entrada and ahora - entrada["loaded_at"] < TTL_SECONDS:
                return list(entrada["cuentas"])

    cuentas = sorted(
        consolidar_cuentas_con_plan_ia(obtener_cuentas(empresa)),
        key=_clave_orden_cuenta,
    )

    with _lock:
        _store[empresa_id] = {
            "loaded_at": ahora,
            "cuentas": cuentas,
        }

    return cuentas


def get_cuentas_cache_info(empresa=None):
    with _lock:
        if empresa is not None:
            empresa_id = str(empresa.get("id") or "default")
            entrada = _store.get(empresa_id)

            if not entrada:
                return None

            return {
                "empresa_id": empresa_id,
                "loaded_at": datetime.fromtimestamp(
                    entrada["loaded_at"],
                    tz=timezone.utc,
                ).isoformat(),
                "num_cuentas": len(entrada.get("cuentas") or []),
                "ttl_seconds": TTL_SECONDS,
                "caduca_en_seconds": max(
                    0,
                    int(TTL_SECONDS - (time.time() - entrada["loaded_at"])),
                ),
                "plan_contable_ia": get_plan_contable_info(),
            }

        return {
            empresa_id: {
                "empresa_id": empresa_id,
                "loaded_at": datetime.fromtimestamp(
                    entrada["loaded_at"],
                    tz=timezone.utc,
                ).isoformat(),
                "num_cuentas": len(entrada.get("cuentas") or []),
                "ttl_seconds": TTL_SECONDS,
                "caduca_en_seconds": max(
                    0,
                    int(TTL_SECONDS - (time.time() - entrada["loaded_at"])),
                ),
            }
            for empresa_id, entrada in _store.items()
        }


def _cuenta_para_ui(cuenta):
    return {
        "codigo": cuenta.get("codigo"),
        "nombre": cuenta.get("nombre"),
        "tipo_etiqueta": cuenta.get("tipo_etiqueta") or cuenta.get("tipo"),
    }


def buscar_cuentas_contables(empresa, texto="", limit=40):
    busqueda = str(texto or "").strip().lower()

    if len(busqueda) < 2:
        return []

    limite = max(1, min(int(limit or 40), 100))
    cuentas = get_cuentas_contables(empresa)
    resultados = []

    for cuenta in cuentas:
        if cuenta_coincide_busqueda(cuenta, busqueda):
            resultados.append(_cuenta_para_ui(cuenta))

            if len(resultados) >= limite:
                break

    return resultados
