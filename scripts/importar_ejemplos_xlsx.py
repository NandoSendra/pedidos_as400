#!/usr/bin/env python3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_asiento import _detectar_tipo_operacion
from asientos_ejemplos_store import guardar_ejemplo


def _normalizar_linea(row):
    cuenta = str(int(row["cuenta"])).zfill(10) if pd.notna(row["cuenta"]) else ""
    dh_raw = int(row["debe_haber"]) if pd.notna(row["debe_haber"]) else 0
    importe = float(row["importe"]) if pd.notna(row["importe"]) else 0.0

    if importe < 0:
        debe_haber = "H" if dh_raw == 0 else "D"
        importe = abs(importe)
    else:
        debe_haber = "D" if dh_raw == 0 else "H"

    concepto = ""

    if pd.notna(row.get("concepto")) and str(row["concepto"]).strip() not in {"", "nan"}:
        concepto = str(row["concepto"]).strip()
    elif pd.notna(row.get("nombre")):
        concepto = str(row["nombre"]).strip()

    programa = str(row["programa"]).strip() if pd.notna(row.get("programa")) else ""

    return {
        "cuenta": cuenta,
        "importe": round(importe, 2),
        "debe_haber": debe_haber,
        "concepto": concepto or "Sin concepto",
        "programa": programa,
        "nombre": str(row.get("nombre", "")).strip(),
    }


def _balance(lineas):
    debe = sum(linea["importe"] for linea in lineas if linea["debe_haber"] == "D")
    haber = sum(linea["importe"] for linea in lineas if linea["debe_haber"] == "H")
    return debe, haber


def _esta_cuadrado(lineas):
    debe, haber = _balance(lineas)
    return len(lineas) >= 2 and abs(debe - haber) < 0.02


def _descripcion_asiento(lineas):
    programa = lineas[0].get("programa", "").strip()
    concepto = lineas[0].get("concepto", "").strip()
    nombre = lineas[0].get("nombre", "").strip()

    if concepto and concepto not in {nombre, "Sin concepto"}:
        detalle = concepto
    elif nombre:
        detalle = nombre
    else:
        detalle = lineas[0].get("cuenta", "")

    if programa:
        return f"{programa}: {detalle}"

    return detalle


def _lineas_para_ejemplo(lineas):
    return [
        {
            "cuenta": linea["cuenta"],
            "importe": linea["importe"],
            "debe_haber": linea["debe_haber"],
            "concepto": linea["concepto"],
        }
        for linea in lineas
        if linea["importe"] > 0
    ]


def _agrupar_por_programa(lineas):
    if not lineas:
        return []

    grupos = []
    actual = [lineas[0]]
    programa = lineas[0].get("programa", "")

    for linea in lineas[1:]:
        if linea.get("programa", "") != programa:
            grupos.append(actual)
            actual = [linea]
            programa = linea.get("programa", "")
        else:
            actual.append(linea)

    grupos.append(actual)
    return grupos


def extraer_asientos_desde_xlsx(ruta_xlsx):
    df = pd.read_excel(ruta_xlsx, header=0)
    df.columns = ["cuenta", "nombre", "debe_haber", "importe", "concepto", "programa"]

    lineas = [
        _normalizar_linea(row)
        for _, row in df.iterrows()
        if pd.notna(row["cuenta"])
    ]
    lineas = [linea for linea in lineas if linea["importe"] > 0]

    asientos = []
    actual = []

    for linea in lineas:
        actual.append(linea)

        if _esta_cuadrado(actual):
            asientos.append(actual)
            actual = []

    if actual:
        for grupo in _agrupar_por_programa(actual):
            if _esta_cuadrado(grupo):
                asientos.append(grupo)

    return asientos


def importar_ejemplos(
    ruta_xlsx,
    empresa_id="default",
    usuario="import-xlsx",
):
    asientos = extraer_asientos_desde_xlsx(ruta_xlsx)
    guardados = []

    for lineas in asientos:
        lineas_ejemplo = _lineas_para_ejemplo(lineas)

        if len(lineas_ejemplo) < 2:
            continue

        descripcion = _descripcion_asiento(lineas)
        tipos = _detectar_tipo_operacion(descripcion)

        ejemplo = guardar_ejemplo(
            empresa_id,
            descripcion,
            lineas_ejemplo,
            usuario=usuario,
            tipos_operacion=tipos,
        )
        guardados.append(ejemplo)

    return guardados


def main():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "asi_mod.xlsx"

    if not ruta.is_file():
        print(f"No existe el fichero: {ruta}", file=sys.stderr)
        sys.exit(1)

    guardados = importar_ejemplos(ruta)
    print(f"Importados {len(guardados)} ejemplos desde {ruta.name}")

    for ejemplo in guardados:
        print(f"- {ejemplo.get('descripcion')} ({len(ejemplo.get('lineas', []))} líneas)")


if __name__ == "__main__":
    main()
