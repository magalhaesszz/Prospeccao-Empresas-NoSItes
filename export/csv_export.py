"""
Exportação de empresas para CSV.
"""
import os, csv, logging
from datetime import datetime

logger = logging.getLogger(__name__)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exportar_csv(empresas, nome_arquivo=None):
    """Gera .csv e retorna o caminho absoluto."""
    if not nome_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"prospecao_{ts}.csv"

    caminho = os.path.join(RAIZ, nome_arquivo)
    campos  = [
        "id", "nome", "telefone", "endereco", "email",
        "tem_site", "score", "status", "mensagem_enviada",
        "nota", "avaliacoes", "descricao_google",
        "preview_url", "data_prospeccao",
    ]

    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        for emp in empresas:
            row = {k: emp.get(k, "") for k in campos}
            row["tem_site"]         = "Sim" if row["tem_site"] else "Não"
            row["mensagem_enviada"] = "Sim" if row["mensagem_enviada"] else "Não"
            writer.writerow(row)

    logger.info("CSV gerado: %s (%d linhas)", caminho, len(empresas))
    return caminho
