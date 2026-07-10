import unittest

from ai_asiento import (
    _intentar_cobro_transferencia_rapida,
    _intentar_completar_cobro_sugerencia,
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


class CobroRapidoTests(unittest.TestCase):
    def test_cobro_a_cliente_por_banco_cuadra(self):
        resultado = _intentar_cobro_transferencia_rapida(
            "Cobro a Bautista Planes por Caixa Popular 1000",
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

        self.assertEqual(lineas[0]["cuenta"], "5720000010")
        self.assertEqual(lineas[0]["debe_haber"], "D")
        self.assertEqual(lineas[1]["cuenta"], "4300001234")
        self.assertEqual(lineas[1]["debe_haber"], "H")
        self.assertEqual(lineas[0]["importe"], 1000.0)
        self.assertEqual(lineas[1]["importe"], 1000.0)

    def test_completar_cobro_con_una_linea_banco(self):
        lineas_ia = [
            {
                "cuenta": "5720000010",
                "fecha": "20260710",
                "importe": 1000,
                "debe_haber": "D",
                "concepto": "Cobro Caixa Popular",
            }
        ]

        completadas = _intentar_completar_cobro_sugerencia(
            "Cobro a Bautista Planes por Caixa Popular 1000",
            lineas_ia,
            CUENTAS,
            "20260710",
        )

        self.assertIsNotNone(completadas)
        lineas = _validar_lineas_sugeridas(
            completadas,
            CUENTAS,
            "20260710",
        )
        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[1]["debe_haber"], "H")


if __name__ == "__main__":
    unittest.main()
