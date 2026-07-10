import unittest
from unittest.mock import patch

from as400_api import (
    LEN_CONCEPTO_ASIENTO,
    crear_asiento_contable,
    normalizar_concepto_asiento,
)
from tests.test_as400_status import FakeResponse


class ConceptoAsientoTests(unittest.TestCase):
    def test_normalizar_concepto_trunca_a_50(self):
        largo = "A" * 80
        concepto = normalizar_concepto_asiento(largo)

        self.assertEqual(len(concepto), LEN_CONCEPTO_ASIENTO)

    def test_ajuste_haber_nombre_largo_cabe_en_as400(self):
        nombre = "NANDO SENDRA EMPRESA DE SERVICIOS INTEGRALES SL"
        concepto = normalizar_concepto_asiento(f"Ajuste Haber {nombre}")

        self.assertLessEqual(len(concepto), LEN_CONCEPTO_ASIENTO)
        self.assertTrue(concepto)

    def test_crear_asiento_envia_concepto_truncado(self):
        respuesta = FakeResponse(
            data={"salida": {"success": "1", "numero_asiento": 7, "mensaje": "OK"}}
        )
        empresa = {
            "id": "1",
            "base_url": "http://example/PEDIDOSCR",
            "endpoints": {"crear_asiento": "/asientos/crear"},
        }

        with patch("as400_api.requests.request", return_value=respuesta) as request_mock:
            crear_asiento_contable(
                empresa,
                "tester",
                [
                    {
                        "cuenta": "4300009999",
                        "fecha": "20260710",
                        "importe": 100,
                        "debe_haber": "D",
                        "concepto": "X" * 80,
                    },
                    {
                        "cuenta": "5720000010",
                        "fecha": "20260710",
                        "importe": 100,
                        "debe_haber": "H",
                        "concepto": "Cobro",
                    },
                ],
            )

        payload = request_mock.call_args.kwargs["json"]
        self.assertEqual(len(payload["lineas"][0]["concepto"]), 50)
        self.assertEqual(payload["lineas"][0]["cuenta"], "4300009999")


if __name__ == "__main__":
    unittest.main()
