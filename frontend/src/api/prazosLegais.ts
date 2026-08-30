import { useQuery } from '@tanstack/react-query'
import api from './client'

export interface PrazoLegal {
  chave: string
  rotulo: string
  /** null = a lei não fixa dias (juiz arbitra, ou o ato vai dentro de outro prazo) */
  dias: number | null
  contagem: 'uteis' | 'corridos' | null
  fundamento: string
  rito: 'comum' | 'juizado' | 'especial'
  destaque: boolean
  observacao: string | null
  pecas: string[]
}

export interface SugestaoPrazo {
  chave: string
  rotulo: string
  dias: number | null
  contagem: 'uteis' | 'corridos' | null
  fundamento: string
  observacao: string | null
}

export interface CatalogoPrazos {
  aviso: string
  principais: PrazoLegal[]
  outros: PrazoLegal[]
  juizados: PrazoLegal[]
  prazos_em_dobro: { quem: string; regra: string; fundamento: string }[]
  regras_contagem: { regra: string; detalhe: string; fundamento: string }[]
  /** chave = rótulo da peça em minúsculas */
  por_peca: Record<string, SugestaoPrazo>
}

export const prazosLegaisApi = {
  catalogo: () => api.get<CatalogoPrazos>('/prazos/legais').then((r) => r.data),
}

/** O catálogo é texto de lei: não muda entre requisições, então fica em cache
 * pela sessão inteira. Compartilhado por todas as telas que usam a legenda. */
export function useCatalogoPrazos() {
  return useQuery({
    queryKey: ['prazos-legais'],
    queryFn: prazosLegaisApi.catalogo,
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

/** Sugestão legal para um rótulo de peça, ou null se não houver. */
export function sugestaoDaPeca(
  catalogo: CatalogoPrazos | undefined,
  peca: string | null | undefined,
): SugestaoPrazo | null {
  if (!catalogo || !peca?.trim()) return null
  return catalogo.por_peca[peca.trim().toLowerCase()] ?? null
}

/** true quando os valores digitados divergem do prazo legal da peça escolhida.
 * Só considera divergência quando a lei fixa dias — peça sem prazo legal
 * (audiência, pedido de dilação) nunca acusa nada. */
export function divergeDaLei(
  sugestao: SugestaoPrazo | null,
  dias: number,
  contagem: string,
): boolean {
  if (!sugestao || sugestao.dias == null) return false
  return sugestao.dias !== dias || (sugestao.contagem != null && sugestao.contagem !== contagem)
}

/** Texto do popup de confirmação quando o usuário sai do prazo legal.
 * Confirmar é permitido de propósito: prazo em dobro, prazo fixado em despacho
 * e contagem própria de Juizado são casos legítimos de divergir da regra geral. */
export function textoConfirmacaoDivergencia(
  sugestao: SugestaoPrazo,
  dias: number,
  contagem: string,
): string {
  const legal = `${sugestao.dias} dia(s) ${sugestao.contagem === 'corridos' ? 'corridos' : 'úteis'}`
  const seu = `${dias} dia(s) ${contagem === 'corridos' ? 'corridos' : 'úteis'}`
  return (
    `Prazo diferente do previsto em lei.\n\n` +
    `${sugestao.rotulo}: ${legal} (${sugestao.fundamento})\n` +
    `Você lançou: ${seu}\n\n` +
    `Isso pode estar certo — prazo em dobro (Fazenda, MP, Defensoria), prazo ` +
    `fixado no próprio despacho ou contagem de Juizado são motivos legítimos.\n\n` +
    `Confirma o prazo que você lançou?`
  )
}
