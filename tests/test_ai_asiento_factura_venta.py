import unittest

from ai_asiento import (
    _extraer_nombre_tercero,
    _intentar_asiento_factura_rapida,
    _resolver_tipos_operacion,
    _validar_lineas_sugeridas,
)


CUENTAS = [
    {
        "codigo": "4300000001",
        "nombre": "MERCADONA SA",
        "tercero_nombre": "MERCADONA",
        "tipo": "cliente",
        "activa": True,
    },
    {
        "codigo": "7000000001",
        "nombre": "Ventas mercaderias",
        "tipo": "ingreso",
        "activa": True,
    },
    {
        "codigo": "4770000021",
        "nombre": "IVA repercutido 21%",
        "tipo": "iva_repercutido",
        "iva_porcentaje": 21,
        "activa": True,
    },
]


class FacturaVentaRapidaTests(unittest.TestCase):
    def test_extrae_mercadona_cuando_me_ha_pagado(self):
        descripcion = (
            "Mercadona me ha pagado una factura de 100 euros al 21% de Iva"
        )

        self.assertEqual(_extraer_nombre_tercero(descripcion), "mercadona")

    def test_factura_venta_con_tipo_forzado(self):
        descripcion = (
            "Mercadona me ha pagado una factura de 100 euros al 21% de Iva"
        )
        tipos = _resolver_tipos_operacion(descripcion, "factura_venta")

        resultado = _intentar_asiento_factura_rapida(
            descripcion,
            CUENTAS,
            "20260714",
            tipos_operacion=tipos,
        )

        self.assertIsNotNone(resultado)
        lineas = _validar_lineas_sugeridas(
            resultado["lineas"],
            CUENTAS,
            "20260714",
        )

        self.assertEqual(len(lineas), 3)
        self.assertEqual(lineas[0]["cuenta"], "4300000001")
        self.assertEqual(lineas[0]["debe_haber"], "D")
        self.assertEqual(lineas[0]["importe"], 121.0)
        self.assertEqual(lineas[1]["cuenta"], "7000000001")
        self.assertEqual(lineas[1]["debe_haber"], "H")
        self.assertEqual(lineas[1]["importe"], 100.0)
        self.assertEqual(lineas[2]["cuenta"], "4770000021")
        self.assertEqual(lineas[2]["debe_haber"], "H")
        self.assertEqual(lineas[2]["importe"], 21.0)


if __name__ == "__main__":
    unittest.main()
