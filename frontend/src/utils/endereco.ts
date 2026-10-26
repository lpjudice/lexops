import type { Cliente } from '../api/clientes'

type CampoEndereco = Pick<
  Cliente,
  'endereco' | 'logradouro' | 'numero' | 'complemento' | 'bairro' | 'cidade' | 'uf' | 'cep'
>

/**
 * Endereço em linha única para documentos (contrato/procuração). Prefere os campos
 * estruturados do cadastro (é o que o autocadastro preenche); cai no texto livre
 * `endereco` dos cadastros antigos.
 */
export function enderecoCompleto(c?: Partial<CampoEndereco> | null): string {
  if (!c) return ''
  const t = (v?: string | null) => (v ?? '').trim()
  if (t(c.logradouro)) {
    const rua = [t(c.logradouro), t(c.numero) && `nº ${t(c.numero)}`, t(c.complemento)].filter(Boolean).join(', ')
    const cidadeUf = [t(c.cidade), t(c.uf)].filter(Boolean).join('/')
    return [rua, t(c.bairro), cidadeUf, t(c.cep) && `CEP ${t(c.cep)}`].filter(Boolean).join(', ')
  }
  return t(c.endereco)
}
