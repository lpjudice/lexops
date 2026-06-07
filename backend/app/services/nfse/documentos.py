"""Validação e formatação de CPF/CNPJ (inclui CNPJ alfanumérico — vigente a partir de 2026)."""
import re


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def so_alfanum(v: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", v or "").upper()


def _valor_char(c: str) -> int:
    # CNPJ alfanumérico: valor = ASCII - 48 (0-9 → 0-9; A-Z → 17-42)
    return ord(c.upper()) - 48


def valida_cnpj_alfa(cnpj: str) -> bool:
    """Valida CNPJ alfanumérico (12 posições alfanuméricas + 2 dígitos DV)."""
    c = so_alfanum(cnpj)
    if len(c) != 14:
        return False
    if not c[12].isdigit() or not c[13].isdigit():
        return False
    base = c[:12]
    if not re.fullmatch(r"[0-9A-Z]{12}", base):
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(_valor_char(c[i]) * pesos[i] for i in range(pos))
        dig = soma % 11
        dig = 0 if dig < 2 else 11 - dig
        if dig != int(c[pos]):
            return False
    return True


def valida_cpf(cpf: str) -> bool:
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[n]) * ((i + 1) - n) for n in range(i))
        dig = (soma * 10) % 11
        dig = 0 if dig == 10 else dig
        if dig != int(cpf[i]):
            return False
    return True


def valida_cnpj(cnpj: str) -> bool:
    cnpj = so_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(pos))
        dig = soma % 11
        dig = 0 if dig < 2 else 11 - dig
        if dig != int(cnpj[pos]):
            return False
    return True


def valida_documento(doc: str) -> tuple[bool, str]:
    """Retorna (valido, tipo). tipo em {'CPF','CNPJ',''}."""
    d = so_digitos(doc)
    if len(d) == 11:
        return valida_cpf(d), "CPF"
    a = so_alfanum(doc)
    if len(a) == 14:
        # numérico tradicional OU alfanumérico (a partir de 2026)
        if a.isdigit():
            return valida_cnpj(a), "CNPJ"
        return valida_cnpj_alfa(a), "CNPJ"
    return False, ""


def formata_documento(doc: str) -> str:
    a = so_alfanum(doc)
    if len(a) == 11 and a.isdigit():
        return f"{a[:3]}.{a[3:6]}.{a[6:9]}-{a[9:]}"
    if len(a) == 14:
        return f"{a[:2]}.{a[2:5]}.{a[5:8]}/{a[8:12]}-{a[12:]}"
    return doc or ""
