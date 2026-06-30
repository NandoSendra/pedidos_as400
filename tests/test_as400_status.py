import unittest
from unittest.mock import patch

import as400_api


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = text

    def json(self):
        return self._data


class AS400StatusTests(unittest.TestCase):
    def setUp(self):
        self.empresa = {
            "id": "01",
            "nombre": "Empresa Test",
            "base_url": "http://as400.test/PEDIDOS",
            "contabilidad_base_url": "http://as400.test/IAERP",
            "endpoints": {
                "proveedores": "/proveedores",
                "cuentas": "/cuentas",
            },
        }

    def test_estado_ok_proveedores(self):
        respuesta = FakeResponse(
            data={
                "salida": {
                    "success": True,
                    "proveedores": [],
                    "numProveedores": 0,
                }
            }
        )

        with patch("as400_api.requests.request", return_value=respuesta):
            proveedores = as400_api.obtener_proveedores(self.empresa)

        estado = as400_api.get_as400_status()
        self.assertEqual(proveedores, [])
        self.assertEqual(estado["servicios"]["pedidos"]["estado"], "ok")
        self.assertEqual(estado["operaciones"]["proveedores"]["estado"], "ok")

    def test_estado_error_http(self):
        respuesta = FakeResponse(status_code=500, text="Fallo AS400")

        with patch("as400_api.requests.request", return_value=respuesta):
            with self.assertRaises(as400_api.AS400ApiError):
                as400_api.obtener_proveedores(self.empresa)

        estado = as400_api.get_as400_status()
        self.assertEqual(estado["servicios"]["pedidos"]["estado"], "error")
        self.assertTrue(estado["errores_recientes"])
        self.assertIn("Fallo AS400", estado["errores_recientes"][0]["error"])


if __name__ == "__main__":
    unittest.main()
