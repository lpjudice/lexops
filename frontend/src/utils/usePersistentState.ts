import { useCallback, useEffect, useRef, useState } from 'react'

// useState que sobrevive a recarga/descarte da aba. Antes, filtros e o processo
// aberto viviam só em useState: se o navegador recarregasse a página ao voltar de
// outra aba (ex.: depois de abrir um arquivo do Drive), tudo voltava ao zero.
//
// Guarda em sessionStorage (por aba): sobrevive a F5 e ao navegador descartar a
// aba para economizar memória, e some quando a aba é fechada — não deixa uma
// seleção antiga "grudada" para sempre como o localStorage deixaria.
//
// A chave pode mudar (ex.: um estado por processo); o valor é relido do storage
// quando isso acontece.
const PREFIXO = 'lexops:ui:'

function ler<T>(chave: string, inicial: T): T {
  try {
    const bruto = sessionStorage.getItem(PREFIXO + chave)
    if (bruto !== null) return JSON.parse(bruto) as T
  } catch {
    // storage indisponível (janela privada) ou JSON inválido: usa o valor inicial
  }
  return inicial
}

export function usePersistentState<T>(chave: string, inicial: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [valor, setValor] = useState<T>(() => ler(chave, inicial))
  const chaveAtual = useRef(chave)

  // Chave mudou (ex.: outro processo): carrega o valor guardado dessa nova chave.
  useEffect(() => {
    if (chaveAtual.current !== chave) {
      chaveAtual.current = chave
      setValor(ler(chave, inicial))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave])

  const atualizar = useCallback(
    (v: T | ((prev: T) => T)) => {
      setValor((prev) => {
        const novo = typeof v === 'function' ? (v as (p: T) => T)(prev) : v
        try {
          sessionStorage.setItem(PREFIXO + chaveAtual.current, JSON.stringify(novo))
        } catch {
          // sem persistência: o estado continua valendo enquanto a página estiver aberta
        }
        return novo
      })
    },
    [],
  )

  return [valor, atualizar]
}
