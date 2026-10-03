"""
Script para importar dados da planilha APEX para o banco de dados da Carteira.
Execução: python -m app.scripts.seed_carteira
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date
import pandas as pd
from decimal import Decimal

# Adiciona o diretório backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import SessionLocal
from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebentureadotEmissao,
    CarteiraDebenturePosicao,
    CarteiraImobiliarioEmpreendimento,
    CarteiraImobiliarioPosicao,
    CarteiraFundoReferencia,
    CarteiraFundoPosicao,
)

DB = SessionLocal()
XLSX_PATH = Path(__file__).parent.parent.parent.parent.parent / "downloads" / "Distribuicao Carteira_Investidores_APEX .xlsx"


def seed_clientes():
    """Importa clientes únicos da planilha"""
    print("📥 Importando clientes...")

    try:
        df = pd.read_excel(XLSX_PATH, sheet_name="Clientes Únicos")
    except Exception as e:
        print(f"⚠️ Erro ao ler 'Clientes Únicos': {e}. Pulando...")
        return

    for _, row in df.iterrows():
        nome = str(row.get("Nome", "")).strip()
        if not nome or nome.lower() == "nan":
            continue

        # Verificar se cliente já existe
        existing = DB.query(CarteiraCliente).filter(
            CarteiraCliente.observacoes.like(f"%{nome}%")
        ).first()

        if existing:
            print(f"  ⏭️ {nome} (já existe)")
            continue

        cliente = CarteiraCliente(
            usuario_cliente_id=hash(nome) % 1000000,  # Pseudo-ID
            cpf=str(row.get("CPF", "")).strip() or None,
            tipo_pessoa="PF",
            email=str(row.get("Email", "")).strip() or None,
            observacoes=f"Importado de Clientes Únicos: {nome}",
            ativo=True,
        )
        DB.add(cliente)
        print(f"  ✅ {nome}")

    DB.commit()
    print(f"✅ {DB.query(CarteiraCliente).count()} clientes na carteira\n")


def seed_emissoes():
    """Importa emissões de debêntures da planilha"""
    print("📥 Importando emissões de debêntures...")

    try:
        df = pd.read_excel(XLSX_PATH, sheet_name="Matriz Cautelas x Emissões")
    except Exception as e:
        print(f"⚠️ Erro ao ler 'Matriz': {e}. Pulando...")
        return

    emissoes_criadas = set()

    for _, row in df.iterrows():
        serie = str(row.get("Série", "")).strip()
        numero = str(row.get("Número Emissão", "")).strip()

        if not serie or serie.lower() == "nan":
            continue

        chave = f"{serie}-{numero}"
        if chave in emissoes_criadas:
            continue

        # Verificar se já existe
        existing = DB.query(CarteiraDebentureadotEmissao).filter(
            CarteiraDebentureadotEmissao.nome_serie == serie
        ).first()

        if existing:
            print(f"  ⏭️ {chave} (já existe)")
            emissoes_criadas.add(chave)
            continue

        emissao = CarteiraDebentureadotEmissao(
            nome_serie=serie,
            numero_emissao=int(numero) if numero.isdigit() else 1,
            emissor="Rhino Securitizadora S/A",
            cnpj_emissor="XX.XXX.XXX/0001-XX",
            indexador=str(row.get("Indexador", "CDI")).strip(),
            taxa_adicional=str(row.get("Taxa Adicional", "")).strip() or None,
            data_vencimento_previsto=pd.to_datetime(row.get("Data Vencimento")) if pd.notna(row.get("Data Vencimento")) else None,
            prazo_carencia_dias=int(row.get("Carência (meses)", 0)) or None,
            resgate_antecipado_emissao=True,
            resgate_antecipado_termo=True,
            ativo=True,
        )
        DB.add(emissao)
        emissoes_criadas.add(chave)
        print(f"  ✅ {chave}")

    DB.commit()
    print(f"✅ {DB.query(CarteiraDebentureadotEmissao).count()} emissões criadas\n")


def seed_debentures():
    """Importa posições de debêntures do Consolidado"""
    print("📥 Importando posições de debêntures...")

    try:
        df = pd.read_excel(XLSX_PATH, sheet_name="Consolidado")
    except Exception as e:
        print(f"⚠️ Erro ao ler 'Consolidado': {e}. Pulando...")
        return

    debenture_count = 0

    for _, row in df.iterrows():
        categoria = str(row.get("Categoria", "")).strip().lower()
        if "rhino" not in categoria and "cautela" not in str(row.get("Nº Conta / Cautela", "")).strip():
            continue

        investidor = str(row.get("Investidor", "")).strip()
        cautela = str(row.get("Nº Conta / Cautela", "")).strip()
        serie = str(row.get("Fundo / Estrutura", "")).strip()

        if not investidor or investidor.lower() == "nan":
            continue

        # Procurar cliente (simplificado)
        cliente = DB.query(CarteiraCliente).filter(
            CarteiraCliente.observacoes.like(f"%{investidor[:20]}%")
        ).first()

        if not cliente:
            # Criar cliente se não existir
            cliente = CarteiraCliente(
                usuario_cliente_id=hash(investidor) % 1000000,
                email=None,
                observacoes=f"Auto-criado: {investidor}",
                ativo=True,
            )
            DB.add(cliente)
            DB.commit()

        # Procurar emissão
        emissao = None
        if serie and serie.lower() != "nan":
            # Tentar encontrar por série
            emissao = DB.query(CarteiraDebentureadotEmissao).filter(
                CarteiraDebentureadotEmissao.nome_serie.like(f"%{serie[:20]}%")
            ).first()

        if not emissao:
            # Criar emissão default
            emissao = CarteiraDebentureadotEmissao(
                nome_serie=serie[:50] if serie and serie.lower() != "nan" else "DEFAULT",
                numero_emissao=1,
                emissor="Rhino Securitizadora",
                ativo=True,
            )
            DB.add(emissao)
            DB.commit()

        # Criar posição
        valor_aplicado = row.get("Valor Aplicado", 0)
        if isinstance(valor_aplicado, str):
            valor_aplicado = valor_aplicado.replace("R$", "").replace(".", "").replace(",", ".")
        valor_aplicado = float(valor_aplicado) if valor_aplicado else 0

        posicao = CarteiraDebenturePosicao(
            cliente_id=cliente.id,
            emissao_id=emissao.id,
            numero_cautela=cautela if cautela and cautela.lower() != "nan" else "-",
            valor_aplicado=valor_aplicado,
            data_aquisicao=pd.to_datetime(row.get("Data da Aplicação")) if pd.notna(row.get("Data da Aplicação")) else date.today(),
            data_base_valor_atual=pd.to_datetime(row.get("Mês de Referência")) if pd.notna(row.get("Mês de Referência")) else None,
            valor_atual_estimado=float(str(row.get("Valor Líquido Julho/26 (R$)", 0)).replace("R$", "").replace(".", "").replace(",", ".")) if row.get("Valor Líquido Julho/26 (R$)") else 0,
            status_resgate="Ativo",
            observacoes=str(row.get("Observações", "")).strip() or None,
            ativo=True,
        )
        DB.add(posicao)
        debenture_count += 1

        if debenture_count % 50 == 0:
            print(f"  {debenture_count} posições processadas...")

    DB.commit()
    print(f"✅ {debenture_count} posições de debêntures criadas\n")


def seed_empreendimentos():
    """Importa empreendimentos imobiliários"""
    print("📥 Importando empreendimentos imobiliários...")

    try:
        df = pd.read_excel(XLSX_PATH, sheet_name="Relacao ABM -- Empreendimento")
    except Exception as e:
        print(f"⚠️ Erro ao ler 'Relacao ABM': {e}. Pulando...")
        return

    for _, row in df.iterrows():
        nome_venda = str(row.get("Nome Venda", "")).strip()
        if not nome_venda or nome_venda.lower() == "nan":
            continue

        existing = DB.query(CarteiraImobiliarioEmpreendimento).filter(
            CarteiraImobiliarioEmpreendimento.nome_venda == nome_venda
        ).first()

        if existing:
            print(f"  ⏭️ {nome_venda} (já existe)")
            continue

        empreendimento = CarteiraImobiliarioEmpreendimento(
            nome_venda=nome_venda,
            nome_razao_social=str(row.get("Razão Social", "")).strip() or None,
            tipo_desenvolvimento="Desenvolvimento Residencial",  # Default
            abmparse_veiculo=str(row.get("ABM-PARSE", "")).strip() or None,
            ativo=True,
        )
        DB.add(empreendimento)
        print(f"  ✅ {nome_venda}")

    DB.commit()
    print(f"✅ {DB.query(CarteiraImobiliarioEmpreendimento).count()} empreendimentos criados\n")


def seed_fundos():
    """Importa fundos de referência"""
    print("📥 Importando fundos de referência...")

    fundos_conhecidos = [
        {"nome": "BRM Carbyne Crédito Estruturado FIC FIDC", "gestora": "BRM", "tipo": "FIDC"},
        {"nome": "Carbyne Cred Priv FI Mult", "gestora": "Carbyne", "tipo": "Multimercado"},
        {"nome": "Carbyne Mercados Privados FC FI Mult CP", "gestora": "Carbyne", "tipo": "Multimercado"},
        {"nome": "BRM Carbyne Voyage FIA", "gestora": "BRM", "tipo": "FIA"},
        {"nome": "FII Apex MS CI ER (APXM11)", "gestora": "Apex", "tipo": "FII"},
    ]

    for fundo_info in fundos_conhecidos:
        existing = DB.query(CarteiraFundoReferencia).filter(
            CarteiraFundoReferencia.nome_fundo == fundo_info["nome"]
        ).first()

        if existing:
            print(f"  ⏭️ {fundo_info['nome']} (já existe)")
            continue

        fundo = CarteiraFundoReferencia(
            nome_fundo=fundo_info["nome"],
            gestora=fundo_info["gestora"],
            tipo_fundo=fundo_info["tipo"],
            ativo=True,
        )
        DB.add(fundo)
        print(f"  ✅ {fundo_info['nome']}")

    DB.commit()
    print(f"✅ {DB.query(CarteiraFundoReferencia).count()} fundos criados\n")


def main():
    """Executa seed completo"""
    print("\n" + "="*60)
    print("🌱 SEED DA CARTEIRA")
    print("="*60 + "\n")

    try:
        seed_clientes()
        seed_emissoes()
        seed_empreendimentos()
        seed_fundos()
        seed_debentures()

        print("\n" + "="*60)
        print("✅ SEED COMPLETO!")
        print("="*60)

        # Resumo
        print(f"\n📊 Resumo:")
        print(f"  • Clientes: {DB.query(CarteiraCliente).count()}")
        print(f"  • Emissões: {DB.query(CarteiraDebentureadotEmissao).count()}")
        print(f"  • Debêntures: {DB.query(CarteiraDebenturePosicao).count()}")
        print(f"  • Empreendimentos: {DB.query(CarteiraImobiliarioEmpreendimento).count()}")
        print(f"  • Fundos: {DB.query(CarteiraFundoReferencia).count()}")

    except Exception as e:
        print(f"\n❌ Erro durante seed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        DB.close()


if __name__ == "__main__":
    main()
