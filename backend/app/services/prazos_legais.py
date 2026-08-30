"""Catálogo de prazos processuais — fonte única da legenda e do auto-preenchimento.

Serve a duas coisas ao mesmo tempo, e é por isso que mora no backend em vez de
ser uma tabela no front:

1. a **legenda** (chip nos menus Prazos / Diário Oficial / Recorte Digital), que
   o Lucas abre pra conferir se o prazo lançado numa publicação está certo;
2. a **sugestão automática** — escolheu "Contestação", o formulário já vem com
   15 dias úteis e o fundamento à vista.

As duas precisam contar a MESMA história: uma legenda que diverge do que o
sistema preenche é pior do que não ter legenda nenhuma.

⚠️ LIMITE DESTE CATÁLOGO — o que ele é e o que ele não é.
Ele guarda a DURAÇÃO do prazo e o artigo. Ele NÃO decide o **termo inicial**,
que é onde mora a maior parte dos erros reais de contagem (juntada do AR,
audiência de conciliação frustrada, publicação no diário, carga dos autos...).
Também não aplica sozinho as contagens **em dobro** (Fazenda Pública, MP,
Defensoria, litisconsortes com procuradores distintos em autos físicos).
Por isso cada verbete traz `observacao` e a UI mostra tudo como *sugestão
conferível*, nunca como resultado fechado.

Base: CPC/2015 (Lei 13.105/2015), Lei 9.099/95, Lei 10.259/01, Lei 12.153/09,
Lei 12.016/09 e Lei 6.830/80.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Regra-mãe da contagem: art. 219 do CPC manda contar só dias úteis, e só para
# prazo PROCESSUAL. Prazo material (decadencial/prescricional) corre corrido —
# por isso entradas como ação rescisória e MS aparecem com contagem "corridos".
CONTAGEM_PADRAO = "uteis"


@dataclass
class PrazoLegal:
    chave: str
    rotulo: str
    # None = a lei não fixa número de dias (o juiz arbitra, ou o ato é praticado
    # dentro de outro prazo). Nesse caso a UI não sugere nada automaticamente.
    dias: int | None
    contagem: str
    fundamento: str
    rito: str          # "comum" | "juizado" | "especial"
    destaque: bool     # True = "principal", aparece na primeira seção da legenda
    observacao: str | None = None
    # Rótulos do select "Peça necessária" que casam com este verbete. É a ponte
    # com a UI: sem isso, a sugestão automática não sabe o que preencher.
    pecas: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Procedimento comum — CPC/2015
# ─────────────────────────────────────────────────────────────────────────────
_COMUM: list[PrazoLegal] = [
    PrazoLegal(
        "contestacao", "Contestação", 15, "uteis", "CPC, art. 335", "comum", True,
        "Termo inicial variável (art. 335, I a III): da audiência de conciliação "
        "frustrada, do protocolo do pedido de cancelamento da audiência pelo réu, "
        "ou da juntada do aviso de recebimento/mandado. Fazenda Pública: 30 dias "
        "úteis (art. 183). Reconvenção e alegação de incompetência vão na própria "
        "contestação (arts. 343 e 337).",
        # "contestacao" (minúsculo, sem acento) é o valor do enum tipo_prazo que
        # a IA do Despacho devolve — mapeado aqui pra sugestão funcionar tanto
        # com o select da tela quanto com a saída da IA.
        ["Contestação", "contestacao"],
    ),
    PrazoLegal(
        "apelacao", "Apelação", 15, "uteis", "CPC, art. 1.003, §5º", "comum", True,
        "Regra geral dos recursos: 15 dias úteis. A única exceção no CPC são os "
        "embargos de declaração (5 dias).",
        # "recurso" genérico da IA cai aqui: 15 dias é a regra geral de todos os
        # recursos do CPC, então é a sugestão certa mesmo sem saber qual é.
        ["Recurso de Apelação", "recurso"],
    ),
    PrazoLegal(
        "contrarrazoes_apelacao", "Contrarrazões de apelação", 15, "uteis",
        "CPC, art. 1.010, §1º", "comum", True,
        "Mesmo prazo para o recurso adesivo, que é interposto na peça de "
        "contrarrazões (art. 997, §2º, I).",
        ["Contrarrazões de Apelação", "Contrarrazões", "contrarrazoes"],
    ),
    PrazoLegal(
        "embargos_declaracao", "Embargos de declaração", 5, "uteis",
        "CPC, art. 1.023", "comum", True,
        "INTERROMPEM o prazo dos demais recursos (art. 1.026) — interrompido, o "
        "prazo recomeça do zero, não do ponto em que parou.",
        ["Embargos de Declaração"],
    ),
    PrazoLegal(
        "agravo_instrumento", "Agravo de instrumento", 15, "uteis",
        "CPC, art. 1.003, §5º c/c art. 1.015", "comum", True,
        "Cabimento restrito às hipóteses do art. 1.015. Contraminuta: 15 dias "
        "(art. 1.019, II).",
        [],
    ),
    PrazoLegal(
        "agravo_interno", "Agravo interno", 15, "uteis", "CPC, art. 1.021, §2º",
        "comum", True, "Contra decisão monocrática do relator.",
        ["Agravo Interno", "Agravo Regimental"],
    ),
    PrazoLegal(
        "replica", "Réplica / impugnação à contestação", 15, "uteis",
        "CPC, arts. 350 e 351", "comum", True,
        "15 dias quando o réu alega fato impeditivo/modificativo/extintivo (art. "
        "350) ou preliminares do art. 337 (art. 351).",
        ["Réplica"],
    ),
    PrazoLegal(
        "recurso_especial", "Recurso especial / extraordinário", 15, "uteis",
        "CPC, art. 1.003, §5º", "comum", True,
        "Agravo em REsp/RE contra decisão que inadmite: também 15 dias (art. 1.042).",
        [],
    ),
    PrazoLegal(
        "recurso_ordinario", "Recurso ordinário", 15, "uteis",
        "CPC, arts. 1.027 e 1.003, §5º", "comum", True, None,
        ["Recurso Ordinário"],
    ),
    PrazoLegal(
        "cumprimento_pagamento", "Cumprimento de sentença — pagamento voluntário",
        15, "uteis", "CPC, art. 523", "comum", True,
        "Não pago no prazo: multa de 10% + honorários de 10% (art. 523, §1º).",
        [],
    ),
    PrazoLegal(
        "impugnacao_cumprimento", "Impugnação ao cumprimento de sentença", 15,
        "uteis", "CPC, art. 525", "comum", True,
        "Corre após o decurso dos 15 dias do art. 523, independentemente de "
        "penhora ou nova intimação.",
        ["Impugnação"],
    ),
    PrazoLegal(
        "embargos_execucao", "Embargos à execução", 15, "uteis", "CPC, art. 915",
        "comum", True, "Contados da juntada do mandado de citação (art. 231).",
        [],
    ),
    PrazoLegal(
        "alegacoes_finais", "Alegações finais / memoriais", 15, "uteis",
        "CPC, art. 364, §2º", "comum", True,
        "Quando a causa é complexa e o juiz substitui o debate oral por memoriais.",
        ["Alegações Finais", "Memorial"],
    ),
    PrazoLegal(
        "prazo_supletivo", "Manifestação sem prazo legal específico", 5, "uteis",
        "CPC, art. 218, §3º", "comum", True,
        "Regra de fechamento: quando a lei é omissa e o juiz não fixou prazo, são "
        "5 dias úteis. É o padrão razoável para uma intimação genérica de "
        '"manifeste-se" — mas CONFIRA se o despacho fixou prazo próprio.',
        ["Manifestação", "Petição Simples", "manifestacao"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Menos frequentes no dia a dia, mas que aparecem
# ─────────────────────────────────────────────────────────────────────────────
_OUTROS: list[PrazoLegal] = [
    PrazoLegal(
        "emenda_inicial", "Emenda à petição inicial", 15, "uteis", "CPC, art. 321",
        "comum", False, "Sob pena de indeferimento da inicial.", [],
    ),
    PrazoLegal(
        "manifestacao_documentos", "Manifestação sobre documento juntado", 15,
        "uteis", "CPC, art. 437, §1º", "comum", False, None, [],
    ),
    PrazoLegal(
        "impugnacao_gratuidade", "Impugnação à gratuidade de justiça", 15, "uteis",
        "CPC, art. 100", "comum", False, None, [],
    ),
    PrazoLegal(
        "suspeicao_impedimento", "Arguição de suspeição / impedimento", 15, "uteis",
        "CPC, art. 146", "comum", False,
        "Contados do conhecimento do fato que gera a suspeição/impedimento.", [],
    ),
    PrazoLegal(
        "embargos_terceiro", "Embargos de terceiro", 5, "uteis", "CPC, art. 675",
        "comum", False,
        "Até 5 dias depois da adjudicação/alienação/arrematação, e sempre ANTES da "
        "assinatura da carta. Na fase de conhecimento, a qualquer tempo até o "
        "trânsito em julgado.", [],
    ),
    PrazoLegal(
        "embargos_monitoria", "Embargos à ação monitória", 15, "uteis",
        "CPC, art. 702", "comum", False,
        "Mesmo prazo do cumprimento do mandado monitório (art. 701).", [],
    ),
    PrazoLegal(
        "execucao_pagamento", "Execução de título extrajudicial — pagamento", 3,
        "uteis", "CPC, art. 829", "comum", False,
        "3 dias para pagar, contados da citação. Pagando nesse prazo, honorários "
        "pela metade (art. 827, §1º).", [],
    ),
    PrazoLegal(
        "inventario_abertura", "Abertura de inventário", 2, "corridos",
        "CPC, art. 611", "especial", False,
        "PRAZO EM MESES, não em dias: 2 meses do óbito para instaurar, e 12 meses "
        "para ultimar. O sistema não calcula prazo em meses — lance a data limite "
        "à mão. Multa por atraso é matéria de lei estadual (ITCMD).", [],
    ),
    PrazoLegal(
        "impugnacao_primeiras_declaracoes",
        "Impugnação às primeiras declarações (inventário)", 15, "uteis",
        "CPC, art. 627", "especial", False, None, [],
    ),
    PrazoLegal(
        "acao_rescisoria", "Ação rescisória", None, "corridos", "CPC, art. 975",
        "especial", False,
        "2 ANOS do trânsito em julgado. Prazo DECADENCIAL e material — corre em "
        "dias corridos e não se suspende em férias/recesso.", [],
    ),
    PrazoLegal(
        "ms_impetracao", "Mandado de segurança — impetração", 120, "corridos",
        "Lei 12.016/09, art. 23", "especial", False,
        "120 dias DECADENCIAIS, contados da ciência do ato impugnado. Corridos, "
        "não úteis — é prazo material.", [],
    ),
    PrazoLegal(
        "ms_informacoes", "Mandado de segurança — informações da autoridade", 10,
        "uteis", "Lei 12.016/09, art. 7º, I", "especial", False, None, [],
    ),
    PrazoLegal(
        "execucao_fiscal_embargos", "Execução fiscal — embargos", 30, "uteis",
        "Lei 6.830/80, art. 16", "especial", False,
        "Contados da intimação da penhora / depósito / juntada da prova da fiança "
        "ou do seguro garantia. Exige garantia do juízo (art. 16, §1º).", [],
    ),
    PrazoLegal(
        "execucao_fiscal_pagamento", "Execução fiscal — pagamento", 5, "uteis",
        "Lei 6.830/80, art. 8º", "especial", False,
        "5 dias para pagar ou garantir a execução.", [],
    ),
    PrazoLegal(
        "audiencia", "Audiência designada", None, None, "—", "comum", False,
        "Não é prazo: é data marcada. Lance a data da audiência como limite. "
        "Atenção à intimação prévia das partes e testemunhas.",
        ["Audiência", "audiencia"],
    ),
    PrazoLegal(
        "pericia", "Perícia", None, None, "CPC, arts. 465 e 477", "comum", False,
        "Não tem prazo único: o juiz fixa o prazo de entrega do laudo (art. 465) "
        "e as partes têm 15 dias para se manifestar sobre ele (art. 477, §1º). "
        "Quesitos e assistente técnico: 15 dias da nomeação (art. 465, §1º).",
        ["pericia"],
    ),
    PrazoLegal(
        "pedido_prazo", "Pedido de dilação de prazo", None, None,
        "CPC, art. 139, VI e art. 222", "comum", False,
        "Não tem prazo próprio — deve ser protocolado ANTES do vencimento do "
        "prazo que se quer dilatar (art. 223: o prazo precluso não se devolve).",
        ["Pedido de Prazo"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Juizados Especiais — a contagem aqui é o ponto mais perigoso
# ─────────────────────────────────────────────────────────────────────────────
_JUIZADOS: list[PrazoLegal] = [
    PrazoLegal(
        "jec_recurso_inominado", "Recurso inominado (JEC)", 10, "uteis",
        "Lei 9.099/95, art. 42", "juizado", True,
        "10 dias da ciência da sentença. ATENÇÃO À CONTAGEM: o Enunciado 165 do "
        "FONAJE orienta contar os prazos do JEC de forma CONTÍNUA (dias corridos), "
        "mas o enunciado não é vinculante e há forte divergência — parte da "
        "jurisprudência aplica o art. 219 do CPC (dias úteis) também nos Juizados. "
        "Confira a orientação da sua Turma Recursal antes de fechar a data.", [],
    ),
    PrazoLegal(
        "jec_contrarrazoes", "Contrarrazões ao recurso inominado (JEC)", 10,
        "uteis", "Lei 9.099/95, art. 42, §2º", "juizado", True,
        "Mesma controvérsia de contagem do recurso inominado.", [],
    ),
    PrazoLegal(
        "jec_embargos_declaracao", "Embargos de declaração (JEC)", 5, "uteis",
        "Lei 9.099/95, art. 50", "juizado", True,
        "Eram 48 horas até o CPC/2015, que alterou o art. 50 para 5 dias e passou "
        "a INTERROMPER o prazo recursal (antes suspendia). Cuidado com material "
        "antigo que ainda repete as 48h.", [],
    ),
    PrazoLegal(
        "jec_contestacao", "Contestação (JEC)", None, None,
        "Lei 9.099/95, arts. 30 e 9º", "juizado", True,
        "NÃO há prazo em dias: a defesa é apresentada NA audiência de instrução e "
        "julgamento, escrita ou oral. Não confunda com o rito comum.", [],
    ),
    PrazoLegal(
        "jec_sem_prazo_dobro", "Juizados — não há prazo em dobro", None, None,
        "Lei 10.259/01, art. 9º; Lei 12.153/09, art. 7º", "juizado", True,
        "Nos Juizados Especiais Federais e da Fazenda Pública NÃO existe prazo "
        "diferenciado para a Fazenda: o ente público responde no mesmo prazo das "
        "demais partes. Erro comum ao migrar do rito comum.", [],
    ),
    PrazoLegal(
        "jef_recurso", "Recurso inominado (JEF / Fazenda)", 10, "uteis",
        "Lei 10.259/01, art. 5º; Lei 12.153/09, art. 4º", "juizado", False,
        "Mesma contagem controvertida do JEC estadual.", [],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Multiplicadores — não são prazos, são regras que alteram qualquer prazo
# ─────────────────────────────────────────────────────────────────────────────
PRAZOS_EM_DOBRO: list[dict[str, str]] = [
    {"quem": "Fazenda Pública (União, Estados, DF, Municípios e autarquias)",
     "regra": "Prazo em dobro para todas as manifestações",
     "fundamento": "CPC, art. 183"},
    {"quem": "Ministério Público",
     "regra": "Prazo em dobro para todas as manifestações",
     "fundamento": "CPC, art. 180"},
    {"quem": "Defensoria Pública e escritórios de prática jurídica",
     "regra": "Prazo em dobro para todas as manifestações",
     "fundamento": "CPC, arts. 186 e 186, §3º"},
    {"quem": "Litisconsortes com procuradores de escritórios DIFERENTES",
     "regra": "Prazo em dobro — SÓ em autos FÍSICOS. Em processo eletrônico "
              "não se aplica (art. 229, §2º), que é a regra hoje.",
     "fundamento": "CPC, art. 229"},
]

REGRAS_CONTAGEM: list[dict[str, str]] = [
    {"regra": "Só dias úteis",
     "detalhe": "Prazo processual em dias conta apenas dias úteis. Não vale para "
                "prazo material (decadencial/prescricional), que corre corrido.",
     "fundamento": "CPC, art. 219"},
    {"regra": "Começa no primeiro dia útil seguinte",
     "detalhe": "Exclui-se o dia do começo e inclui-se o do vencimento; se o "
                "início ou o fim cair em dia não útil, prorroga-se.",
     "fundamento": "CPC, arts. 224 e 224, §1º"},
    {"regra": "Publicação no diário",
     "detalhe": "Considera-se data da publicação o primeiro dia útil seguinte ao "
                "da DISPONIBILIZAÇÃO no Diário da Justiça Eletrônico — e o prazo "
                "só começa a correr no dia útil seguinte a essa publicação.",
     "fundamento": "CPC, art. 224, §§2º e 3º"},
    {"regra": "Suspensão de fim de ano",
     "detalhe": "Entre 20 de dezembro e 20 de janeiro os prazos ficam suspensos.",
     "fundamento": "CPC, art. 220"},
    {"regra": "Embargos de declaração interrompem",
     "detalhe": "Interrompem (não suspendem) o prazo dos demais recursos: ele "
                "recomeça integralmente.",
     "fundamento": "CPC, art. 1.026"},
]

AVISO = (
    "Material de apoio para conferência — não substitui a leitura do despacho. "
    "O catálogo traz a DURAÇÃO legal do prazo; o TERMO INICIAL e eventual "
    "contagem em dobro dependem do caso concreto e precisam ser verificados."
)

TODOS: list[PrazoLegal] = _COMUM + _OUTROS + _JUIZADOS


def _por_peca() -> dict[str, PrazoLegal]:
    """Índice rótulo-da-peça → verbete, para a sugestão automática."""
    idx: dict[str, PrazoLegal] = {}
    for p in TODOS:
        for peca in p.pecas:
            idx.setdefault(peca.strip().lower(), p)
    return idx


def sugestao_para_peca(peca: str | None) -> PrazoLegal | None:
    """Verbete correspondente a um rótulo do select "Peça necessária"."""
    if not peca or not peca.strip():
        return None
    return _por_peca().get(peca.strip().lower())


def catalogo() -> dict:
    """Payload consumido pela legenda e pela sugestão automática no front."""
    return {
        "aviso": AVISO,
        "principais": [asdict(p) for p in TODOS if p.destaque and p.rito != "juizado"],
        "outros": [asdict(p) for p in TODOS if not p.destaque and p.rito != "juizado"],
        "juizados": [asdict(p) for p in TODOS if p.rito == "juizado"],
        "prazos_em_dobro": PRAZOS_EM_DOBRO,
        "regras_contagem": REGRAS_CONTAGEM,
        # Mapa direto peça → sugestão: evita o front reimplementar o casamento.
        "por_peca": {
            peca: {
                "chave": p.chave,
                "rotulo": p.rotulo,
                "dias": p.dias,
                "contagem": p.contagem,
                "fundamento": p.fundamento,
                "observacao": p.observacao,
            }
            for peca, p in _por_peca().items()
        },
    }
