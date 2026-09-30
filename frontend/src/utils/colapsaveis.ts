import { useCallback, useSyncExternalStore } from 'react'

// Estado "recolhido" dos itens expansíveis do Autos IA (grupos de petição +
// documentos na aba Documentos, perguntas do FAQ), guardado por caso no
// navegador. Antes cada item tinha um useState local: ao sair da tela e voltar,
// tudo reabria e o usuário tinha que recolher de novo.
//
// Modelo: cada tipo de item (prefixo "doc", "faq") tem um PADRÃO (aberto, ou
// recolhido depois de "Recolher tudo") e guardamos só as EXCEÇÕES a ele. Assim
// "Recolher tudo" vale também para grupos que ainda não foram carregados
// ("Carregar mais") ou que aparecerem numa sincronização futura.

const chave = (casoId: string) => `lexops:autos-ia:colapsados:${casoId}`
const cache = new Map<string, Set<string>>()
const ouvintes = new Set<() => void>()
const prefixoDe = (id: string) => id.split(':')[0]
const marcaPadraoRecolhido = (prefixo: string) => `*${prefixo}`

function ler(casoId: string): Set<string> {
  const guardado = cache.get(casoId)
  if (guardado) return guardado
  let conjunto = new Set<string>()
  try {
    const bruto = localStorage.getItem(chave(casoId))
    if (bruto) conjunto = new Set<string>(JSON.parse(bruto) as string[])
  } catch {
    // localStorage indisponível (janela privada) ou JSON inválido: começa tudo aberto
  }
  cache.set(casoId, conjunto)
  return conjunto
}

function gravar(casoId: string, conjunto: Set<string>) {
  cache.set(casoId, conjunto)
  try {
    localStorage.setItem(chave(casoId), JSON.stringify([...conjunto]))
  } catch {
    // sem persistência: o estado continua valendo enquanto a página estiver aberta
  }
  ouvintes.forEach((fn) => fn())
}

const assinar = (fn: () => void) => {
  ouvintes.add(fn)
  return () => { ouvintes.delete(fn) }
}

export function useColapsaveis(casoId: string) {
  const estado = useSyncExternalStore(assinar, () => ler(casoId))

  const estaAberto = useCallback((id: string) => {
    const padraoRecolhido = estado.has(marcaPadraoRecolhido(prefixoDe(id)))
    return padraoRecolhido ? estado.has(id) : !estado.has(id)
  }, [estado])

  const alternar = useCallback((id: string) => {
    const novo = new Set(ler(casoId))
    if (!novo.delete(id)) novo.add(id)
    gravar(casoId, novo)
  }, [casoId])

  const definirPadrao = useCallback((prefixo: string, recolhido: boolean) => {
    // zera as exceções do tipo e troca o padrão
    const novo = new Set([...ler(casoId)].filter((id) => prefixoDe(id).replace('*', '') !== prefixo))
    if (recolhido) novo.add(marcaPadraoRecolhido(prefixo))
    gravar(casoId, novo)
  }, [casoId])

  const recolherTodos = useCallback((prefixo: string) => definirPadrao(prefixo, true), [definirPadrao])
  const expandirTodos = useCallback((prefixo: string) => definirPadrao(prefixo, false), [definirPadrao])

  return { estaAberto, alternar, recolherTodos, expandirTodos }
}
