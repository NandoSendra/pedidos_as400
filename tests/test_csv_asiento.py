import unittest

from csv_asiento import parsear_archivo_importacion


class CSVAsientoTests(unittest.TestCase):
    def test_carga_parcial_informa_errores_y_cuentas_no_encontradas(self):
        contenido = (
            "Cuenta;Fecha;Importe;Debe/Haber;Concepto\n"
            "4300000001;2026-06-30;125,40;D;Cliente valido\n"
            "9999999999;2026-06-30;20;H;Cuenta ausente\n"
            "7000000001;2026-06-30;abc;H;Importe mal\n"
        ).encode("utf-8")
        cuentas = [
            {"codigo": "4300000001", "nombre": "Cliente valido"},
            {"codigo": "7000000001", "nombre": "Ventas"},
        ]

        resultado = parsear_archivo_importacion(
            contenido,
            filename="asiento.csv",
            cuentas_plan=cuentas,
        )
        diagnostico = resultado["diagnostico"]

        self.assertEqual(resultado["modo"], "lineas")
        self.assertEqual(len(resultado["lineas"]), 1)
        self.assertEqual(diagnostico["filas_total"], 3)
        self.assertEqual(diagnostico["filas_validas"], 1)
        self.assertEqual(diagnostico["filas_descartadas"], 2)
        self.assertTrue(diagnostico["carga_parcial"])
        self.assertEqual(len(diagnostico["cuentas_no_encontradas"]), 1)
        self.assertEqual(len(diagnostico["errores"]), 1)

    def test_columnas_debe_haber_separadas(self):
        contenido = (
            "Cuenta;Fecha;Debe;Haber;Concepto\n"
            "4300000001;2026-06-30;125,40;;Cargo\n"
            "7000000001;2026-06-30;;125,40;Abono\n"
        ).encode("utf-8")
        cuentas = [
            {"codigo": "4300000001", "nombre": "Cliente"},
            {"codigo": "7000000001", "nombre": "Ventas"},
        ]

        resultado = parsear_archivo_importacion(
            contenido,
            filename="asiento.csv",
            cuentas_plan=cuentas,
        )

        self.assertEqual(resultado["modo"], "lineas")
        self.assertEqual(
            [linea["debe_haber"] for linea in resultado["lineas"]],
            ["D", "H"],
        )


if __name__ == "__main__":
    unittest.main()
