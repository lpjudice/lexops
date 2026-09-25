import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { processosApi } from '../../api/processos'
import { clientesApi } from '../../api/clientes'
import pageStyles from '../../pages/Page.module.css'
import styles from './ProcessoCombobox.module.css'

interface Props {
  value: string
  onChange: (processoId: string) => void
  placeholder?: string
}

/** Combobox com busca por número do processo ou nome do cliente. */
export default function ProcessoCombobox({ value, onChange, placeholder }: Props) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const nomeClientePorId = useMemo(() => {
    const mapa = new Map<string, string>()
    clientes.forEach((c) => mapa.set(c.id, c.nome))
    return mapa
  }, [clientes])

  const selecionado = useMemo(() => processos.find((p) => p.id === value), [processos, value])

  const filtrados = useMemo(() => {
    const termo = busca.trim().toLowerCase()
    if (!termo) return processos.slice(0, 30)
    return processos
      .filter((p) => {
        const nomeCliente = (nomeClientePorId.get(p.cliente_id) || '').toLowerCase()
        return p.numero_cnj.toLowerCase().includes(termo) || nomeCliente.includes(termo)
      })
      .slice(0, 30)
  }, [processos, busca, nomeClientePorId])

  const labelSelecionado = selecionado
    ? `${selecionado.numero_cnj}${nomeClientePorId.get(selecionado.cliente_id) ? ` — ${nomeClientePorId.get(selecionado.cliente_id)}` : ''}`
    : ''

  return (
    <div
      className={styles.wrapper}
      ref={wrapperRef}
      onBlur={(e) => {
        if (!wrapperRef.current?.contains(e.relatedTarget as Node)) {
          setAberto(false)
          setBusca('')
        }
      }}
    >
      <input
        className={pageStyles.input}
        placeholder={placeholder ?? 'Buscar por número do processo ou nome do cliente...'}
        value={aberto ? busca : labelSelecionado}
        onFocus={() => { setAberto(true); setBusca('') }}
        onChange={(e) => setBusca(e.target.value)}
      />
      {value && !aberto && (
        <button
          type="button"
          className={styles.limpar}
          onClick={() => onChange('')}
          title="Remover vínculo"
        >
          ×
        </button>
      )}
      {aberto && (
        <div className={styles.lista}>
          {filtrados.length === 0 ? (
            <div className={styles.vazio}>Nenhum processo encontrado.</div>
          ) : (
            filtrados.map((p) => (
              <div
                key={p.id}
                className={`${styles.item} ${p.id === value ? styles.itemAtivo : ''}`}
                onMouseDown={() => { onChange(p.id); setAberto(false); setBusca('') }}
              >
                <div className={styles.itemNumero}>{p.numero_cnj}</div>
                <div className={styles.itemMeta}>
                  {nomeClientePorId.get(p.cliente_id) || 'Cliente não identificado'}
                  {p.materia ? ` · ${p.materia}` : ''}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
