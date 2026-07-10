import unittest

from cuenta_tipos import enriquecer_cuenta, formatear_cuenta_para_ia, puntuar_busqueda_cuenta
from plan_contable_ia import (
    consolidar_cuenta_con_plan,
    consolidar_cuentas_con_plan_ia,
    get_plan_contable_info,
    plan_contable_disponible,
)


class PlanContableIATests(unittest.TestCase):
    @unittest.skipUnless(plan_contable_disponible(), "Falta plan_contable_IA_PGC_completo.xlsx")
    def test_plan_contable_carga_excel(self):
        info = get_plan_contable_info()

        self.assertTrue(info["existe"])
        self.assertGreater(info["num_pgc"], 100)
        self.assertGreater(info["num_subcuentas"], 10)

    @unittest.skipUnless(plan_contable_disponible(), "Falta plan_contable_IA_PGC_completo.xlsx")
    def test_consolida_cuenta_banco_con_pgc(self):
        cuenta = enriquecer_cuenta({
            "codigo": "5720000010",
            "nombre": "CAIXA POPULAR LA CLAUDIA",
            "activa": True,
        })
        consolidada = consolidar_cuenta_con_plan(cuenta)

        self.assertIn("banco", consolidada.get("palabras_clave", "").lower())
        self.assertIn("pgc", consolidada.get("plan_contable_fuente", ""))

        texto_ia = formatear_cuenta_para_ia(consolidada)
        self.assertIn("claves=", texto_ia)
        self.assertIn("naturaleza=", texto_ia)

    @unittest.skipUnless(plan_contable_disponible(), "Falta plan_contable_IA_PGC_completo.xlsx")
    def test_consolida_subcuenta_por_codigo(self):
        cuenta = enriquecer_cuenta({
            "codigo": "6010000001",
            "nombre": "COMPRA AZUCAR",
            "activa": True,
        })
        consolidada = consolidar_cuenta_con_plan(cuenta)

        self.assertIn("subcuenta", consolidada.get("plan_contable_fuente", ""))
        self.assertIn("azucar", consolidada.get("palabras_clave", "").lower())

    @unittest.skipUnless(plan_contable_disponible(), "Falta plan_contable_IA_PGC_completo.xlsx")
    def test_palabras_excluyentes_penalizan_busqueda(self):
        cuenta = consolidar_cuenta_con_plan(enriquecer_cuenta({
            "codigo": "6020000001",
            "nombre": "ENVASES PRIMARIOS",
            "activa": True,
        }))

        score_ok = puntuar_busqueda_cuenta(cuenta, {"envase"})
        score_malo = puntuar_busqueda_cuenta(cuenta, {"ingrediente"})

        self.assertGreater(score_ok, score_malo)

    def test_sin_plan_devuelve_cuentas_sin_cambios(self):
        cuenta = {"codigo": "9999999999", "nombre": "PRUEBA"}
        resultado = consolidar_cuentas_con_plan_ia([cuenta])

        self.assertEqual(resultado[0]["codigo"], "9999999999")


if __name__ == "__main__":
    unittest.main()
