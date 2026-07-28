"""
Exportação de empresas para arquivo .xlsx via openpyxl.
"""
import os
import logging
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# Pasta raiz do projeto (um nível acima de /export)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exportar_excel(empresas, nome_arquivo=None):
    """
    Gera arquivo .xlsx com as empresas fornecidas.
    Retorna o caminho absoluto do arquivo gerado.
    """
    if not nome_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"prospecao_{ts}.xlsx"

    caminho = os.path.join(RAIZ, nome_arquivo)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Empresas Prospectadas"

    # --- Estilos ---
    fill_cabecalho = PatternFill("solid", fgColor="2563EB")
    fill_sem_site = PatternFill("solid", fgColor="D1FAE5")
    fill_tem_site = PatternFill("solid", fgColor="FEE2E2")
    fill_enviado = PatternFill("solid", fgColor="DBEAFE")

    fonte_cabecalho = Font(bold=True, color="FFFFFF", size=11)
    borda_fina = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # --- Cabeçalho ---
    colunas = [
        "Nome da Empresa",
        "Telefone",
        "Endereço",
        "Tem Site?",
        "Mensagem Enviada?",
    ]
    larguras = [40, 22, 55, 13, 20]

    for col, titulo in enumerate(colunas, start=1):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.font = fonte_cabecalho
        cel.fill = fill_cabecalho
        cel.alignment = Alignment(horizontal="center", vertical="center")
        cel.border = borda_fina

    ws.row_dimensions[1].height = 22

    # --- Dados ---
    for linha, emp in enumerate(empresas, start=2):
        tem_site = bool(emp.get("tem_site"))
        enviado = bool(emp.get("mensagem_enviada"))

        linha_dados = [
            emp.get("nome", ""),
            emp.get("telefone", ""),
            emp.get("endereco", ""),
            "Sim" if tem_site else "Não",
            "Sim" if enviado else "Não",
        ]

        for col, valor in enumerate(linha_dados, start=1):
            cel = ws.cell(row=linha, column=col, value=valor)
            cel.alignment = Alignment(vertical="center", wrap_text=True)
            cel.border = borda_fina

            # Colore célula "Tem Site?"
            if col == 4:
                cel.fill = fill_tem_site if tem_site else fill_sem_site
            # Colore célula "Mensagem Enviada?"
            elif col == 5 and enviado:
                cel.fill = fill_enviado

        ws.row_dimensions[linha].height = 18

    # --- Largura das colunas ---
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura

    # --- Congela a linha de cabeçalho ---
    ws.freeze_panes = "A2"

    wb.save(caminho)
    logger.info("Excel gerado: %s (%d empresas)", caminho, len(empresas))
    return caminho
