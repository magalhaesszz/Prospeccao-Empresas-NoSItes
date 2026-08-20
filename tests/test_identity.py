from prospector.identity import canonical_company,company_fingerprint,maps_place_id,normalize_phone
def test_phone_normalization_br():assert normalize_phone("(62) 99999-1234")=="+5562999991234";assert normalize_phone("+55 62 99999-1234")=="+5562999991234";assert normalize_phone("123") is None
def test_place_identity_variants():assert maps_place_id("https://maps.google.com/?query_place_id=ChIABC123")=="query_place_id:ChIABC123";assert maps_place_id("https://google.com/maps/place/X/data=!4m1!1s0x935ef:0xabc123!8m2")=="0x935ef:0xabc123"
def test_fingerprint_is_normalized_and_stable():
    a=company_fingerprint("Clínica São José","Av. Goiás, 123 - Centro");b=company_fingerprint("Clinica Sao Jose","Av Goiás 123 Centro");assert a==b;assert len(a)==32
def test_canonical_company():
    c=canonical_company({"nome":" Loja X ","telefone":"62 99999-1234","endereco":"Rua 1, 2"});assert c["nome"]=="Loja X";assert c["telefone"]=="+5562999991234";assert c["fingerprint"]
