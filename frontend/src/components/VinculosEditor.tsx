import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import type { Cliente } from '../api/clientes'
import ClienteCombobox from './ClienteCombobox'
import cs from './VinculosEditor.module.css'

interface Props {
  /** Clientes já vinculados (exibidos como chips). */
  vinculados: Cliente[]
  /** Base de clientes para o combobox. */
  clientes: Cliente[]
  /** Cria um cliente inline (raw = "nome|tipo"); retorna o id. */
  onCreateCliente: (raw: string) => Promise<string>
  onAdd: (id: string) => void
  onRemove: (id: string) => void
  /** ids a não oferecer no combobox (ex.: o próprio cliente). */
  excluir?: string[]
  /** navegar ao clicar no chip (detalhe). */
  onAbrir?: (id: string) => void
}

export default function VinculosEditor({
  vinculados, clientes, onCreateCliente, onAdd, onRemove, excluir = [], onAbrir,
}: Props) {
  const jaVinculados = new Set(vinculados.map((v) => v.id))
  const bloqueados = new Set([...excluir, ...jaVinculados])
  const opcoes = clientes.filter((c) => !bloqueados.has(c.id))

  return (
    <div className={cs.root}>
      {vinculados.length > 0 && (
        <div className={cs.chips}>
          {vinculados.map((v) => (
            <span key={v.id} className={cs.chip}>
              {onAbrir ? (
                <button type="button" className={cs.chipNome} onClick={() => onAbrir(v.id)} title="Abrir cadastro">
                  {v.nome}
                </button>
              ) : (
                <span className={cs.chipNome}>{v.nome}</span>
              )}
              <span className={cs.chipTipo}>{v.tipo}</span>
              <button type="button" className={cs.chipRemover} title="Remover vínculo"
                onClick={() => onRemove(v.id)}>×</button>
            </span>
          ))}
        </div>
      )}
      <ClienteCombobox
        value=""
        clientes={opcoes}
        onChange={(id) => { if (id) onAdd(id) }}
        onCreateCliente={onCreateCliente}
      />
    </div>
  )
}

/** Wrapper auto-gerenciado: carrega os vínculos de um cliente e persiste via API. */
export function ClienteVinculos({
  clienteId, clientes, onCreateCliente, onAbrir,
}: {
  clienteId: string
  clientes: Cliente[]
  onCreateCliente: (raw: string) => Promise<string>
  onAbrir?: (id: string) => void
}) {
  const qc = useQueryClient()
  const { data: vinculados = [] } = useQuery({
    queryKey: ['vinculos', clienteId],
    queryFn: () => clientesApi.listarVinculos(clienteId),
  })
  const invalidar = () => qc.invalidateQueries({ queryKey: ['vinculos'] })
  const add = useMutation({
    mutationFn: (id: string) => clientesApi.adicionarVinculo(clienteId, id),
    onSuccess: invalidar,
  })
  const rem = useMutation({
    mutationFn: (id: string) => clientesApi.removerVinculo(clienteId, id),
    onSuccess: invalidar,
  })
  return (
    <VinculosEditor
      vinculados={vinculados}
      clientes={clientes}
      onCreateCliente={onCreateCliente}
      onAdd={(id) => add.mutate(id)}
      onRemove={(id) => rem.mutate(id)}
      excluir={[clienteId]}
      onAbrir={onAbrir}
    />
  )
}
