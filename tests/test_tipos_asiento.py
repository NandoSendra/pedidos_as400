import unittest

from ai_asiento import (
    _intentar_anadir_linea_rapida,
    _longitud_minima_descripcion,
    _resolver_tipos_operacion,
    listar_tipos_asiento,
    normalizar_tipo_asiento_solicitud,
)


CUENTAS_NANDO = [
    {
        "codigo": "4300009999",
        "nombre": "NANDO SENDRA SL",
        "tercero_nombre": "NANDO SENDRA",
        "tipo": "cliente",
        "activa": True,
    },
]


class TiposAsientoTests(unittest.TestCase):
    def test_normalizar_tipo_asiento_ignora_null_json(self):
        self.assertIsNone(normalizar_tipo_asiento_solicitud(None))
        self.assertIsNone(normalizar_tipo_asiento_solicitud("null"))
        self.assertIsNone(normalizar_tipo_asiento_solicitud("None"))
        self.assertIsNone(normalizar_tipo_asiento_solicitud(""))
        self.assertEqual(normalizar_tipo_asiento_solicitud("remesa"), "remesa")
    def test_listar_tipos_asiento_incluye_remesa(self):
        tipos = listar_tipos_asiento()
        ids = [tipo["id"] for tipo in tipos]

        self.assertIn("remesa", ids)
        self.assertTrue(any(tipo["ejemplo"] for tipo in tipos))

    def test_resolver_tipo_usuario_prioriza_seleccion(self):
        tipos = _resolver_tipos_operacion(
            "Bautista Planes Caixa Popular 100",
            "remesa",
        )

        self.assertEqual(tipos[0], "remesa")

    def test_longitud_minima_mas_breve_con_tipo(self):
        self.assertEqual(
            _longitud_minima_descripcion("Bautista 100", "remesa"),
            5,
        )
        self.assertEqual(
            _longitud_minima_descripcion("Bautista 100"),
            10,
        )

    def test_anadir_haber_a_nando_sendra(self):
        lineas_actuales = [
            {
                "cuenta": "5720000010",
                "fecha": "20260710",
                "importe": 100,
                "debe_haber": "D",
                "concepto": "Cobro banco",
            }
        ]
        resultado = _intentar_anadir_linea_rapida(
            "Añade 100 euros al haber a nando sendra",
            lineas_actuales,
            CUENTAS_NANDO,
            "20260710",
        )

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["modo"], "añadir")
        self.assertEqual(resultado["lineas"][0]["debe_haber"], "H")
        self.assertEqual(resultado["lineas"][0]["cuenta"], "4300009999")


if __name__ == "__main__":
    unittest.main()
