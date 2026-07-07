import unittest
from unittest.mock import patch

from as400_api import _normalizar_articulo, obtener_articulos


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "salida": {
                "success": True,
                "numArticulos": 3,
                "articulos": [
                    {"codigo": "A1", "descripcion": "Articulo 1"},
                    {"codigo": "", "descripcion": ""},
                    {"codigo": "A2", "descripcion": "Articulo 2"},
                ],
            }
        }


class FakeTopLevelLineasSalidaResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "lineas_salida": 2,
            "articulos": [
                {"codigo": "A1", "descripcion": "Articulo 1"},
                {"codigo": "A2", "descripcion": "Articulo 2"},
                {"codigo": "A3", "descripcion": "Articulo 3"},
            ],
        }


class ArticulosNormalizacionTests(unittest.TestCase):
    def test_normaliza_alias_de_consumo_y_stock_otros(self):
        articulo = _normalizar_articulo({
            "codigo": "A1",
            "consumo_diario": 3.5,
            "stock_otros": 7,
            "fechaUltimoConsumo": "20260629",
            "fechaUltimo": "20260601",
        })

        self.assertEqual(articulo["Consumo_Diario"], 3.5)
        self.assertEqual(articulo["consumo_diario"], 3.5)
        self.assertEqual(articulo["stockOtros"], 7)
        self.assertEqual(articulo["fecha_ultimo_consumo"], "20260629")
        self.assertEqual(articulo["fecha_ultimo"], "20260601")

    def test_obtener_articulos_ignora_posiciones_vacias(self):
        empresa = {
            "id": "01",
            "base_url": "http://as400.test",
            "endpoints": {"articulos": "/articulos"},
        }

        with patch("as400_api.requests.request", return_value=FakeResponse()):
            articulos = obtener_articulos(empresa, "123", "20260601")

        self.assertEqual([articulo["codigo"] for articulo in articulos], ["A1", "A2"])

    def test_obtener_articulos_respeta_lineas_salida_sin_salida(self):
        empresa = {
            "id": "01",
            "base_url": "http://as400.test",
            "endpoints": {"articulos": "/articulos"},
        }

        with patch(
            "as400_api.requests.request",
            return_value=FakeTopLevelLineasSalidaResponse(),
        ):
            articulos = obtener_articulos(empresa, "123", "20260601")

        self.assertEqual([articulo["codigo"] for articulo in articulos], ["A1", "A2"])


if __name__ == "__main__":
    unittest.main()
