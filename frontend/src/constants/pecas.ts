import type { RitoProcesso } from '../api/processos'

/** Peças do rito comum (CPC) — os rótulos aqui precisam casar com o campo
 * `pecas` dos verbetes em `backend/app/services/prazos_legais.py` pra sugestão
 * automática de prazo funcionar. */
export const PECAS_COMUM = [
  'Agravo de Instrumento', 'Agravo Interno', 'Agravo em Recurso Especial', 'Agravo em Recurso Extraordinário',
  'Alegações Finais', 'Audiência', 'Contestação', 'Contrarrazões', 'Contrarrazões de Agravo',
  'Contrarrazões de Apelação', 'Cumprimento de Sentença', 'Embargos de Declaração', 'Embargos de Divergência',
  'Embargos Infringentes', 'Exceção de Pré-Executividade', 'Impugnação', 'Impugnação ao Cumprimento de Sentença',
  'Manifestação', 'Memorial', 'Petição Intermediária', 'Quesitos', 'Recurso de Apelação', 'Recurso Especial',
  'Recurso Extraordinário', 'Recurso Ordinário', 'Réplica',
].sort((a, b) => a.localeCompare(b, 'pt-BR'))

/** Peças dos Juizados Especiais — contagem e prazos diferentes do rito comum
 * (Lei 9.099/95, Lei 10.259/01, Lei 12.153/09). Rótulos distintos dos do rito
 * comum de propósito, pra não colidir na busca por peça do catálogo legal. */
export const PECAS_JUIZADO_CIVIL = [
  'Audiência', 'Contestação (JEC)', 'Contrarrazões (JEC)', 'Contrarrazões em Juizado Especial',
  'Embargos de Declaração (JEC)', 'Impugnação ao Cumprimento de Sentença (JEC)', 'Manifestação',
  'Recurso Inominado (JEC)',
].sort((a, b) => a.localeCompare(b, 'pt-BR'))

export const PECAS_JUIZADO_FEDERAL_FAZENDA = [
  'Audiência', 'Contestação (JEC)', 'Contrarrazões (JEF/Fazenda)', 'Manifestação',
  'Recurso Inominado (JEF/Fazenda)',
].sort((a, b) => a.localeCompare(b, 'pt-BR'))

export const PECAS_JUIZADO_CRIMINAL = [
  'Apelação (Juizado Especial Criminal)', 'Audiência', 'Contrarrazões (Juizado Especial Criminal)',
  'Manifestação',
].sort((a, b) => a.localeCompare(b, 'pt-BR'))

export const RITO_OPTS: Array<{ value: RitoProcesso; label: string }> = [
  { value: 'comum', label: 'Justiça comum' },
  { value: 'juizado_especial_civil', label: 'Juizado Especial Civil (JEC)' },
  { value: 'juizado_especial_criminal', label: 'Juizado Especial Criminal' },
  { value: 'juizado_especial_federal', label: 'Juizado Especial Federal (JEF)' },
  { value: 'juizado_especial_fazenda', label: 'Juizado Especial da Fazenda Pública' },
]

export const RITO_LABEL: Record<RitoProcesso, string> = Object.fromEntries(
  RITO_OPTS.map((o) => [o.value, o.label]),
) as Record<RitoProcesso, string>

/** Lista de peças a oferecer no combobox, de acordo com o rito do processo. */
export function pecasPara(rito: RitoProcesso | null | undefined): string[] {
  switch (rito) {
    case 'juizado_especial_civil': return PECAS_JUIZADO_CIVIL
    case 'juizado_especial_federal':
    case 'juizado_especial_fazenda': return PECAS_JUIZADO_FEDERAL_FAZENDA
    case 'juizado_especial_criminal': return PECAS_JUIZADO_CRIMINAL
    default: return PECAS_COMUM
  }
}

export function ehJuizado(rito: RitoProcesso | null | undefined): boolean {
  return !!rito && rito !== 'comum'
}
