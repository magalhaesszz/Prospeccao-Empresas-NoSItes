from prospector.inbound import is_optout,parse_evolution,parse_meta
def test_optout_detection():assert is_optout("Não quero receber mais mensagens");assert is_optout("PARAR");assert not is_optout("Pode me mandar mais detalhes?")
def test_parse_evolution_ignores_from_me():
    assert parse_evolution({"data":{"key":{"fromMe":True,"remoteJid":"5562999999999@s.whatsapp.net"},"message":{"conversation":"x"}}}) is None;m=parse_evolution({"data":{"key":{"fromMe":False,"remoteJid":"5562999999999@s.whatsapp.net","id":"m1"},"message":{"conversation":"Olá"}}});assert m.phone=="+5562999999999" and m.text=="Olá"
def test_parse_meta_text():
    items=parse_meta({"entry":[{"changes":[{"value":{"messages":[{"id":"m1","from":"5562999999999","type":"text","text":{"body":"Oi"}}]}}]}]});assert len(items)==1 and items[0].text=="Oi"
