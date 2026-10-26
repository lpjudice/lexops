"""Leitura do organograma societário em PDF vetorial (como o "Doc. 06 — Organograma Grupo Apex").

O PDF é desenhado por programa (não é imagem): cada empresa é uma caixa arredondada com nome e CNPJ,
cada vínculo é uma linha poligonal que sai da base da controladora (com uma setinha) e chega ao topo da
controlada, e o percentual de participação é uma etiqueta sobre a linha. Por isso a estrutura sai da
GEOMETRIA — sem IA e sem adivinhar — e o resultado é conferível contra o desenho.

A tela é muito alta e o PDF a divide em páginas que repetem o mesmo desenho deslocado: o desenho inteiro é
reconstruído juntando as páginas (cada página desloca o desenho em uma altura de página).
"""
import io
import re
from collections import OrderedDict

RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_PCT = re.compile(r"^\d{1,3}(?:,\d{1,2})?%$")


def _cor(c):
    try:
        return tuple(round(float(v), 2) for v in c) if c else None
    except TypeError:
        return None


def _dist_seg(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _elementos(pagina):
    """(curvas, retângulos, caracteres) da página, com y contado do topo."""
    from pdfminer.layout import LTChar, LTCurve, LTRect

    alt = pagina.height
    curvas, rects, chars = [], [], []

    def visita(o):
        if isinstance(o, LTChar):
            chars.append({"t": o.get_text(), "x0": o.x0, "x1": o.x1, "top": alt - o.y1, "bottom": alt - o.y0})
        elif isinstance(o, LTRect):
            rects.append({"x0": o.x0, "x1": o.x1, "top": alt - o.y1, "bottom": alt - o.y0, "fill": o.fill})
        elif isinstance(o, LTCurve):
            path = getattr(o, "original_path", None) or []
            fechada = bool(path) and path[-1][0] == "h"
            curvas.append({
                "x0": o.x0, "x1": o.x1, "top": alt - o.y1, "bottom": alt - o.y0, "pts": [(x, alt - y) for x, y in o.pts],
                "fechada": fechada, "fill": o.fill, "lw": o.linewidth, "cor": _cor(o.stroking_color),
                "tracejado": bool(o.dashing_style and o.dashing_style[0]),
            })
        if hasattr(o, "__iter__"):
            for f in o:
                visita(f)

    visita(pagina)
    return curvas, rects, chars


def _texto_em(chars, x0, x1, top, bottom, folga=1.5, excluir=()) -> str:
    cs = [c for c in chars if c["x0"] >= x0 - folga and c["x1"] <= x1 + folga and c["top"] >= top - folga and c["bottom"] <= bottom + folga
          and not any(c["x0"] >= r["x0"] - 1 and c["x1"] <= r["x1"] + 1 and c["top"] >= r["top"] - 2 and c["bottom"] <= r["bottom"] + 2 for r in excluir)]
    linhas: "OrderedDict[int, list]" = OrderedDict()
    for c in sorted(cs, key=lambda c: (round(c["top"]), c["x0"])):
        linhas.setdefault(round(c["top"]), []).append(c)
    out = []
    for cs_l in linhas.values():
        s = ""
        for i, c in enumerate(cs_l):
            if i and c["x0"] - cs_l[i - 1]["x1"] > 1.2:
                s += " "
            s += c["t"]
        out.append(s.strip())
    return " ".join(x for x in out if x)


def ler(pdf_bytes: bytes) -> dict:
    """{'nos': [{cnpj, nome, cor}], 'relacoes': [{pai, filho, pct, tracejado}], 'avisos': [...]}"""
    from pdfminer.high_level import extract_pages

    try:
        paginas = list(extract_pages(io.BytesIO(pdf_bytes)))
    except Exception as exc:  # noqa: BLE001 — arquivo que não é PDF / corrompido
        raise ValueError(f"Não consegui ler o PDF: {str(exc)[:120]}")
    if not paginas:
        raise ValueError("PDF vazio.")
    altura = paginas[0].height
    nos: dict[tuple, dict] = {}
    arestas: dict[tuple, dict] = {}
    etiquetas: list[dict] = []
    for pi, pag in enumerate(paginas):
        dy = pi * altura
        curvas, rects, chars = _elementos(pag)
        pequenos = [r for r in rects if r["x1"] - r["x0"] < 40 and r["bottom"] - r["top"] < 12 and r["top"] > 30]
        for c in curvas:
            if c["fill"] and abs((c["lw"] or 0) - 1.1) < 0.01 and c["x1"] - c["x0"] > 60:
                texto = _texto_em(chars, c["x0"], c["x1"], c["top"], c["bottom"], excluir=pequenos)
                m = RE_CNPJ.search(texto)
                if not m:
                    continue
                # o percentual desenhado sobre a caixa não faz parte do nome
                nome = re.sub(r"\b\d{1,3}(?:,\d{1,2})?%", "", RE_CNPJ.sub("", texto))
                nome = re.sub(r"\s+", " ", nome).strip()
                nos.setdefault((round(c["x0"]), round(c["top"] + dy)), {
                    "x0": c["x0"], "x1": c["x1"], "top": c["top"] + dy, "bottom": c["bottom"] + dy, "cnpj": m.group(0), "nome": nome, "cor": c["cor"]})
            elif not c["fechada"] and not c["fill"] and len(c["pts"]) >= 2:
                pts = tuple((round(x, 1), round(y + dy, 1)) for x, y in c["pts"])
                arestas[pts] = {"pts": list(pts), "tracejado": c["tracejado"]}
        for r in rects:
            if r["x1"] - r["x0"] < 40 and r["bottom"] - r["top"] < 12 and r["top"] > 30:
                t = _texto_em(chars, r["x0"], r["x1"], r["top"], r["bottom"], folga=2)
                if RE_PCT.match(t):
                    etiquetas.append({"x": (r["x0"] + r["x1"]) / 2, "y": (r["top"] + r["bottom"]) / 2 + dy, "pct": t})
    lista = list(nos.values())
    if not lista:
        raise ValueError("Nenhuma empresa (caixa com CNPJ) encontrada no PDF.")

    def acha(x, y, lado):
        melhor = None
        for n in lista:
            if n["x0"] - 2 <= x <= n["x1"] + 2:
                d = abs((n["bottom"] if lado == "base" else n["top"]) - y)
                if d <= 6 and (melhor is None or d < melhor[0]):
                    melhor = (d, n)
        return melhor[1] if melhor else None

    rel, avisos, aresta_de = [], [], []
    for e in arestas.values():
        pai, filho = acha(*e["pts"][0], "base"), acha(*e["pts"][-1], "topo")
        if pai is None or filho is None:
            avisos.append(f"Linha sem empresa numa das pontas: {e['pts'][0]} → {e['pts'][-1]}")
            continue
        rel.append({"pai": pai["cnpj"], "filho": filho["cnpj"], "tracejado": e["tracejado"], "pct": None})
        aresta_de.append(e)
    # etiqueta de percentual → linha mais próxima (1 para 1, da menor distância para a maior)
    pares = []
    for i, e in enumerate(aresta_de):
        for j, l in enumerate(etiquetas):
            d = min(_dist_seg(l["x"], l["y"], e["pts"][k], e["pts"][k + 1]) for k in range(len(e["pts"]) - 1))
            if d <= 30:
                pares.append((d, i, j))
    pares.sort()
    ei, lj = set(), set()
    for d, i, j in pares:
        if i in ei or j in lj:
            continue
        ei.add(i); lj.add(j)
        rel[i]["pct"] = etiquetas[j]["pct"]
    sem = sum(1 for r in rel if r["pct"] is None)
    if sem:
        avisos.append(f"{sem} vínculo(s) sem percentual identificável no desenho.")
    nomes = {n["cnpj"]: n for n in lista}
    return {"nos": [{"cnpj": n["cnpj"], "nome": n["nome"], "cor": n["cor"]} for n in nomes.values()],
            "relacoes": rel, "avisos": avisos}
