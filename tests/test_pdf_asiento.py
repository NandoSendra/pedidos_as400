import unittest

from pdf_asiento import (
    construir_resumen_pdf,
    extraer_datos_factura,
    inferir_tipo_documento,
)


TEXTO_FACTURA_COMPRA = """
FACTURA DE COMPRA
Proveedor: GARCÍA SUMINISTROS SL
NIF B12345678
Base imponible: 1.000,00 €
IVA 21%: 210,00 €
Total factura: 1.210,00 €
Factura nº 2026/045
Fecha: 10/07/2026
"""

TEXTO_FACTURA_VENTA = """
FACTURA DE VENTA
Cliente: MERCADONA SA
Base imponible 500,00
IVA repercutido 21% 105,00
Importe total 605,00
"""


class PDFAsientoTests(unittest.TestCase):
    def test_extrae_importes_factura_compra(self):
        datos = extraer_datos_factura(TEXTO_FACTURA_COMPRA)

        self.assertEqual(datos["base_imponible"], 1000.0)
        self.assertEqual(datos["cuota_iva"], 210.0)
        self.assertEqual(datos["total"], 1210.0)
        self.assertEqual(datos["tipo_iva"], 21)

    def test_infiere_factura_compra(self):
        tipo = inferir_tipo_documento(TEXTO_FACTURA_COMPRA)

        self.assertEqual(tipo, "factura_compra")

    def test_infiere_factura_venta(self):
        tipo = inferir_tipo_documento(TEXTO_FACTURA_VENTA)

        self.assertEqual(tipo, "factura_venta")

    def test_tipo_usuario_tiene_prioridad(self):
        tipo = inferir_tipo_documento(TEXTO_FACTURA_COMPRA, tipo_usuario="gasto")

        self.assertEqual(tipo, "gasto")

    def test_construye_resumen_para_ia(self):
        datos = extraer_datos_factura(TEXTO_FACTURA_COMPRA)
        resumen = construir_resumen_pdf(
            TEXTO_FACTURA_COMPRA,
            datos,
            tipo_documento="factura_compra",
            num_paginas=1,
            nombre_archivo="factura.pdf",
        )

        self.assertIn("DOCUMENTO PDF", resumen)
        self.assertIn("Base imponible: 1000.00", resumen)
        self.assertIn("Factura de compra", resumen)
        self.assertIn("TEXTO EXTRAÍDO DEL PDF", resumen)


if __name__ == "__main__":
    unittest.main()
