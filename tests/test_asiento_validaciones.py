import unittest
from unittest.mock import patch

import app as app_module


class AsientoValidacionesTests(unittest.TestCase):
    def setUp(self):
        self.empresa = {"id": "01", "nombre": "Empresa Test"}
        self.cuentas = [
            {
                "codigo": "4770000001",
                "nombre": "IVA repercutido",
                "tipo": "iva_repercutido",
                "activa": True,
            },
            {
                "codigo": "7000000001",
                "nombre": "Ventas",
                "tipo": "ventas",
                "activa": True,
            },
            {
                "codigo": "4300000001",
                "nombre": "Clientes varios",
                "tipo": "cliente",
                "activa": False,
                "generica": True,
            },
        ]

    def test_advertencias_asiento_enriquecidas(self):
        payload = {
            "lineas": [
                {
                    "cuenta": "4770000001",
                    "fecha": "2026-06-30",
                    "importe": 21,
                    "debe_haber": "D",
                    "concepto": "IVA mal ubicado",
                },
                {
                    "cuenta": "7000000001",
                    "fecha": "2026-06-30",
                    "importe": 21,
                    "debe_haber": "H",
                    "concepto": "Venta",
                },
                {
                    "cuenta": "4300000001",
                    "fecha": "2026-06-30",
                    "importe": 10,
                    "debe_haber": "D",
                    "concepto": "Cliente generico",
                },
                {
                    "cuenta": "7000000001",
                    "fecha": "2026-06-30",
                    "importe": 10,
                    "debe_haber": "H",
                    "concepto": "Venta",
                },
            ],
        }

        with patch.object(app_module, "get_cuentas_contables", return_value=self.cuentas):
            lineas, advertencias = app_module._normalizar_lineas_asiento_para_confirmar(
                payload,
                self.empresa,
            )

        texto = " ".join(advertencias).lower()
        self.assertEqual(len(lineas), 4)
        self.assertIn("iva repercutido", texto)
        self.assertIn("inactiva", texto)
        self.assertIn("genérica", texto)

    def test_cuenta_inexistente_no_se_confirma(self):
        payload = {
            "lineas": [
                {
                    "cuenta": "9999999999",
                    "fecha": "2026-06-30",
                    "importe": 1,
                    "debe_haber": "D",
                    "concepto": "No existe",
                },
                {
                    "cuenta": "7000000001",
                    "fecha": "2026-06-30",
                    "importe": 1,
                    "debe_haber": "H",
                    "concepto": "Venta",
                },
            ],
        }

        with patch.object(app_module, "get_cuentas_contables", return_value=self.cuentas):
            with self.assertRaises(ValueError):
                app_module._normalizar_lineas_asiento_para_confirmar(
                    payload,
                    self.empresa,
                )


if __name__ == "__main__":
    unittest.main()
