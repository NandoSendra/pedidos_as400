import unittest
from unittest.mock import patch

from cuentas_cache import _store, _lock, buscar_cuentas_contables


CUENTAS_DESORDENADAS = [
    {"codigo": "5720000010", "nombre": "CAIXA POPULAR", "activa": True},
    {"codigo": "4300000001", "nombre": "CLIENTE A", "activa": True},
    {"codigo": "4000000099", "nombre": "PROVEEDOR Z", "activa": True},
    {"codigo": "4300000002", "nombre": "CLIENTE B", "activa": True},
]


class CuentasCacheOrdenTests(unittest.TestCase):
    def setUp(self):
        with _lock:
            _store.clear()

    def tearDown(self):
        with _lock:
            _store.clear()

    @patch("cuentas_cache.obtener_cuentas", return_value=CUENTAS_DESORDENADAS)
    def test_buscar_cuentas_devuelve_orden_por_codigo(self, _mock_obtener):
        empresa = {"id": "1"}

        resultados = buscar_cuentas_contables(empresa, "43", limit=10)
        codigos = [item["codigo"] for item in resultados]

        self.assertEqual(codigos, ["4300000001", "4300000002"])


if __name__ == "__main__":
    unittest.main()
