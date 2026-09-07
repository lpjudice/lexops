/** Trata o 409 "nome_similar" que o backend devolve ao tentar criar um cliente
 * parecido com um já cadastrado. Compartilhado entre todo fluxo que cria
 * cliente (cadastro direto, aprovação de autocadastro, contratantes de
 * contrato lidos por IA) para dar a mesma experiência em todos eles. */
export interface ClienteSimilar {
  id: string
  nome: string
  tipo: 'PF' | 'PJ'
  similaridade: number
}

/** null = usuário confirmou que é a MESMA pessoa (cancela a criação).
 * string = usuário confirmou que é diferente; nome sugerido para seguir. */
export function confirmarNomeSimilar(nomeDigitado: string, similares: ClienteSimilar[]): string | null {
  const lista = similares
    .map((s) => `• ${s.nome} (${s.tipo}) — ${Math.round(s.similaridade * 100)}% parecido`)
    .join('\n')
  const ehMesmoCliente = window.confirm(
    `Já existe um cadastro parecido com "${nomeDigitado}":\n\n${lista}\n\n` +
    `É a MESMA pessoa/empresa?\n\n` +
    `OK = sim, é a mesma (cancela este cadastro — use o cliente já existente)\n` +
    `Cancelar = não, é diferente (seguir com o cadastro)`
  )
  if (ehMesmoCliente) return null
  const sugestao = window.prompt(
    'Pessoa/empresa diferente. Para evitar confundir as pastas de cada uma, ' +
    'complete o nome com um identificador (cidade, apelido, etc.):',
    nomeDigitado,
  )
  return sugestao && sugestao.trim() ? sugestao.trim() : null
}

export function isNomeSimilarConflict(err: unknown): ClienteSimilar[] | null {
  const resp = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (resp?.status !== 409) return null
  const detail = resp.data?.detail as { tipo?: string; similares?: ClienteSimilar[] } | undefined
  return detail?.tipo === 'nome_similar' ? (detail.similares ?? []) : null
}
