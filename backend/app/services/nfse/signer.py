"""Assinatura digital XMLDSIG da DPS (e eventos) com o e-CNPJ A1, via xmlsec.

Usamos python-xmlsec (libxmlsec1) porque seu C14N casa exatamente com o validador
do governo. Implementação manual com lxml produzia C14N ligeiramente diferente,
rejeitada com E0714. xmlsec também emite a Signature no namespace default (sem
prefixo `ds:`), evitando o E1228.

Padrão NFS-e Nacional:
- Reference URI = "#<Id do infDPS/infPedReg>"
- Transforms: enveloped-signature + C14N inclusiva (REC-xml-c14n-20010315)
- RSA-SHA1 + SHA1 (padrão aceito pelo Sefin Nacional)
- KeyInfo com X509Certificate
"""
from __future__ import annotations

from lxml import etree
import xmlsec

from .client import load_cert_and_key

NFSE_NS = "http://www.sped.fazenda.gov.br/nfse"


def _assinar(xml_bytes: bytes, inf_tag: str) -> bytes:
    root = etree.fromstring(xml_bytes)
    inf = root.find(f"{{{NFSE_NS}}}{inf_tag}")
    if inf is None:
        inf = root.find(inf_tag)
    if inf is None:
        raise ValueError(f"{inf_tag} não encontrado no XML")
    ref_id = inf.get("Id")

    # Registra "Id" como atributo de identificação (para resolver URI="#Id")
    xmlsec.tree.add_ids(root, ["Id"])

    # Template da assinatura (ns=None → namespace default, sem prefixo ds:)
    sig = xmlsec.template.create(
        root,
        c14n_method=xmlsec.constants.TransformInclC14N,
        sign_method=xmlsec.constants.TransformRsaSha1,
        ns=None,
    )
    root.append(sig)

    ref = xmlsec.template.add_reference(
        sig, xmlsec.constants.TransformSha1, uri=f"#{ref_id}"
    )
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformEnveloped)
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformInclC14N)

    ki = xmlsec.template.ensure_key_info(sig)
    xmlsec.template.add_x509_data(ki)

    cert_pem, key_pem = load_cert_and_key()
    key = xmlsec.Key.from_memory(key_pem, xmlsec.constants.KeyDataFormatPem)
    key.load_cert_from_memory(cert_pem, xmlsec.constants.KeyDataFormatPem)

    ctx = xmlsec.SignatureContext()
    ctx.key = key
    ctx.sign(sig)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def assinar_dps(dps_xml: bytes) -> bytes:
    return _assinar(dps_xml, "infDPS")


def assinar_evento(evento_xml: bytes) -> bytes:
    return _assinar(evento_xml, "infPedReg")
