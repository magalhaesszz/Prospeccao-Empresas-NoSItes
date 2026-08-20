from prospector.landing import build_preview
from prospector.scoring import has_own_website,lead_score
def test_social_is_not_own_website():assert not has_own_website("https://instagram.com/acme");assert has_own_website("https://acme.com.br")
def test_score_rewards_contact_and_no_site():assert lead_score({"tem_site":False,"telefone":"+5562999999999","nota":4.8,"avaliacoes":120,"descricao_google":"Clínica odontológica"})>=80
def test_landing_escapes_content():
    slug,markup=build_preview({"nome":"<script>x</script>","telefone":"+5562999999999"});assert "<script>x</script>" not in markup;assert "&lt;script&gt;" in markup;assert slug
