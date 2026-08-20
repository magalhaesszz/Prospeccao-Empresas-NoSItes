import unittest
from utils.identity import company_fingerprint, company_identity_key, maps_place_id, normalize_phone


class IdentityTests(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(normalize_phone("(11) 99999-0000"), "+5511999990000")

    def test_place_id(self):
        url = "https://www.google.com/maps/place/x/data=!4m2!3m1!1sChIJabcDEF_123"
        self.assertEqual(maps_place_id(url), "ChIJabcDEF_123")

    def test_fingerprint_stable(self):
        a = company_fingerprint("Clínica São José", "Rua A, 123")
        b = company_fingerprint("clinica sao jose", "Rua A 123")
        self.assertEqual(a, b)

    def test_identity_priority(self):
        key = company_identity_key({"nome": "X", "endereco": "Rua Longa 123", "telefone": "11999990000"})
        self.assertTrue(key.startswith("phone:"))


if __name__ == "__main__":
    unittest.main()
