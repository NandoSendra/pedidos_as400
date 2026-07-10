import unittest

from ai_asiento import (
    _intentar_asiento_desde_ejemplo_aprendido,
    _intentar_remesa_transferencia_rapida,
    _validar_lineas_sugeridas,
)


CUENTAS = [
    {
        "codigo": "5720000010",
        "nombre": "CAIXA POPULAR LA CLAUDIA",
        "tipo": "banco",
        "activa": True,
    },
    {
        "codigo": "4300001234",
        "nombre": "BAUTISTA PLANES SL",
        "tercero_nombre": "BAUTISTA PLANES",
        "tipo": "cliente",
        "activa": True,
    },
]


class RemesaRapidaTests(unittest.TestCase):
    def test_remesa_a_tercero_por_banco_cuadra(self):
        resultado = _intentar_remesa_transferencia_rapida(
            "Remesa a Bautista Planes por Caixa Popular por 100 euros",
            CUENTAS,
            "20260710",
        )

        self.assertIsNotNone(resultado)
        self.assertEqual(len(resultado["lineas"]), 2)

        lineas = _validar_lineas_sugeridas(
            resultado["lineas"],
            CUENTAS,
            "20260710",
        )

        self.assertEqual(lineas[0]["cuenta"], "4300001234")
        self.assertEqual(lineas[0]["debe_haber"], "D")
        self.assertEqual(lineas[1]["cuenta"], "5720000010")
        self.assertEqual(lineas[1]["debe_haber"], "H")
        self.assertEqual(lineas[0]["importe"], 100.0)
        self.assertEqual(lineas[1]["importe"], 100.0)
        self.assertTrue(lineas[0]["concepto"].startswith("Remesa"))

    def test_remesa_de_cliente_por_banco_cuadra(self):
        resultado = _intentar_remesa_transferencia_rapida(
            "Remesa de Bautista Planes por Caixa Popular 250",
            CUENTAS,
            "20260710",
        )

        self.assertIsNotNone(resultado)
        lineas = _validar_lineas_sugeridas(
            resultado["lineas"],
            CUENTAS,
            "20260710",
        )

        self.assertEqual(lineas[0]["cuenta"], "5720000010")
        self.assertEqual(lineas[0]["debe_haber"], "D")
        self.assertEqual(lineas[1]["cuenta"], "4300001234")
        self.assertEqual(lineas[1]["debe_haber"], "H")

    def test_validacion_rellena_concepto_vacio_desde_plan(self):
        lineas = _validar_lineas_sugeridas(
            [
                {
                    "cuenta": "5720000010",
                    "fecha": "20260710",
                    "importe": 100,
                    "debe_haber": "D",
                    "concepto": "",
                },
                {
                    "cuenta": "4300001234",
                    "fecha": "20260710",
                    "importe": 100,
                    "debe_haber": "H",
                    "concepto": "Cobro cliente",
                },
            ],
            CUENTAS,
            "20260710",
        )

        self.assertEqual(lineas[0]["concepto"], "CAIXA POPULAR LA CLAUDIA")


class RemesaEjemploAprendidoTests(unittest.TestCase):
    def test_reutiliza_ejemplo_con_importe_distinto(self):
        from unittest.mock import patch

        ejemplo = {
            "descripcion": "Remesa a Bautista Planes por Caixa Popular",
            "tipos_operacion": ["Remesa", "Pago"],
            "lineas": [
                {
                    "cuenta": "4300001234",
                    "importe": 1000,
                    "debe_haber": "D",
                    "concepto": "Remesa BAUTISTA PLANES",
                },
                {
                    "cuenta": "5720000010",
                    "importe": 1000,
                    "debe_haber": "H",
                    "concepto": "Remesa Caixa Popular",
                },
            ],
        }

        with patch(
            "ai_asiento._seleccionar_ejemplos_similares",
            return_value=[ejemplo],
        ), patch(
            "ai_asiento._puntuar_ejemplo_similitud",
            return_value=120,
        ):
            resultado = _intentar_asiento_desde_ejemplo_aprendido(
                "Remesa a Bautista Planes por Caixa Popular por 100 euros",
                CUENTAS,
                "20260710",
                "23",
            )

        self.assertIsNotNone(resultado)
        lineas = _validar_lineas_sugeridas(
            resultado["lineas"],
            CUENTAS,
            "20260710",
        )
        self.assertEqual(lineas[0]["importe"], 100.0)
        self.assertEqual(lineas[1]["importe"], 100.0)


if __name__ == "__main__":
    unittest.main()
