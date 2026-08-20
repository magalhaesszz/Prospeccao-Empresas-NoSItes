import types
import unittest

from database.prospecting_meta import ExistingCompany, adapt_known_company
from scraper.prospecting import enhanced_score, has_own_website, install


class ProspectingExtensionTests(unittest.TestCase):
    def test_social_profile_is_not_own_website(self):
        self.assertFalse(has_own_website("https://instagram.com/empresa"))
        self.assertFalse(has_own_website("https://m.facebook.com/empresa"))
        self.assertTrue(has_own_website("https://empresa.com.br"))

    def test_score_only_adds_to_legacy_logic(self):
        def old_score(company, categoria=""):
            return 40
        company = {"nota": 4.8, "avaliacoes": 150}
        self.assertEqual(enhanced_score(old_score, company, "dentista"), 55)

    def test_known_company_is_adapted_for_legacy_dedup(self):
        company = {"nome": "Empresa", "telefone": None, "maps_url": "nova-url"}
        existing = ExistingCompany(7, "Empresa", "+5511999999999", "Rua A", "url-antiga", "contatado", 1)
        adapt_known_company(company, existing)
        self.assertEqual(company["telefone"], "+5511999999999")
        self.assertEqual(company["mensagem_enviada"], 1)
        self.assertTrue(company["_duplicado"])

    def test_install_preserves_legacy_functions(self):
        gm = types.SimpleNamespace()
        gm.buscar_empresas = lambda *a, **k: ["legacy"]
        gm._calcular_score = lambda company, categoria="": 10
        install(gm)
        self.assertTrue(gm._PROSPECT_EXTENSIONS_INSTALLED)
        self.assertTrue(callable(gm.buscar_empresas_legado))
        self.assertTrue(callable(gm._calcular_score_legado))
        self.assertEqual(gm._calcular_score({"nota": 5, "avaliacoes": 100}, "x"), 25)


if __name__ == "__main__":
    unittest.main()
