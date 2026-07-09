import unittest
from unittest.mock import patch

from as400_api import obtener_almacenes_pedido, obtener_articulos


class FakeAlmacenesResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "IAERPCR_Get_almacenes_R": [
                {"CODIGO": 1, "NOMBRE": "Central"},
                {"CODIGO": 0, "NOMBRE": "Invalido"},
                {"CODIGO": 2, "NOMBRE": "Secundario"},
            ]
        }


class FakeArticulosResponse:
    status_code = 200
    text = ""

    def __init__(self, params):
        self.params = params

    def json(self):
        return {
            "salida": {
                "success": True,
                "numArticulos": 1,
                "articulos": [{"codigo": "A1", "descripcion": "Articulo 1"}],
            }
        }


class AlmacenesPedidoTests(unittest.TestCase):
    def test_obtener_almacenes_pedido_normaliza_respuesta_iaerp(self):
        empresa = {
            "id": "1",
            "url_almacenes": "http://as400.test/IAERP/almacenes",
        }

        with patch(
            "as400_api.requests.request",
            return_value=FakeAlmacenesResponse(),
        ) as request_mock:
            almacenes = obtener_almacenes_pedido(empresa)

        self.assertEqual(
            almacenes,
            [
                {"codigo": 1, "nombre": "Central"},
                {"codigo": 2, "nombre": "Secundario"},
            ],
        )
        self.assertEqual([item["codigo"] for item in almacenes], [1, 2])
        request_mock.assert_called_once()
        self.assertEqual(
            request_mock.call_args.kwargs["url"],
            "http://as400.test/IAERP/almacenes",
        )

    def test_obtener_almacenes_pedido_conserva_orden_api(self):
        empresa = {
            "id": "1",
            "url_almacenes": "http://as400.test/IAERP/almacenes",
        }

        class RespuestaOrdenApi:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "IAERPCR_Get_almacenes_R": [
                        {"CODIGO": 1, "NOMBRE": "Central"},
                        {"CODIGO": 131, "NOMBRE": "Auto 1"},
                        {"CODIGO": 100, "NOMBRE": "Tenerife"},
                    ]
                }

        with patch(
            "as400_api.requests.request",
            return_value=RespuestaOrdenApi(),
        ):
            almacenes = obtener_almacenes_pedido(empresa)

        self.assertEqual([item["codigo"] for item in almacenes], [1, 131, 100])

    def test_obtener_articulos_envia_intervalo_y_almacen(self):
        empresa = {
            "id": "01",
            "base_url": "http://as400.test",
            "endpoints": {"articulos": "/articulos"},
        }

        with patch("as400_api.requests.request") as request_mock:
            request_mock.return_value = FakeArticulosResponse({})
            articulos = obtener_articulos(
                empresa,
                "123",
                fecha_desde="20260101",
                fecha_hasta="20260630",
                almacen="5",
            )

        self.assertEqual([item["codigo"] for item in articulos], ["A1"])
        url = request_mock.call_args.kwargs["url"]
        self.assertIn("fechaAnalisisDesde=20260101", url)
        self.assertIn("fechaAnalisisHasta=20260630", url)
        self.assertIn("almacen=5", url)

    def test_obtener_articulos_rechaza_intervalo_invertido(self):
        empresa = {
            "id": "01",
            "base_url": "http://as400.test",
            "endpoints": {"articulos": "/articulos"},
        }

        with self.assertRaisesRegex(Exception, "fecha desde"):
            obtener_articulos(
                empresa,
                "123",
                fecha_desde="20261201",
                fecha_hasta="20260101",
                almacen="1",
            )

    def test_obtener_articulos_requiere_almacen(self):
        empresa = {
            "id": "01",
            "base_url": "http://as400.test",
            "endpoints": {"articulos": "/articulos"},
        }

        with self.assertRaisesRegex(Exception, "almac"):
            obtener_articulos(empresa, "123", fecha_desde="20260101", fecha_hasta="20260630")


if __name__ == "__main__":
    unittest.main()
