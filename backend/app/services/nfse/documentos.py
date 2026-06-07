"""Validação e formatação de CPF/CNPJ."""
import re


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


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
    if len(d) == 14:
        return valida_cnpj(d), "CNPJ"
    return False, ""


def formata_documento(doc: str) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc or ""
