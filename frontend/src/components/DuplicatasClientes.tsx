import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import type { ClienteDuplicataGrupo } from '../api/clientes'
import cs from './DuplicatasClientes.module.css'

function fmtData(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleDateString('pt-BR')
}

/** Canônico sugerido: quem já tem pasta no Drive; empate/nenhum → o mais antigo. */
function sugerirCanonico(grupo: ClienteDuplicataGrupo): string {
  const comPasta = grupo.membros.find((m) => m.drive_folder_id)
  if (comPasta) return comPasta.id
  return [...grupo.membros].sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''))[0].id
}

function GrupoDuplicata({ grupo, onMesclado }: { grupo: ClienteDuplicataGrupo; onMesclado: () => void }) {
  const [canonicalId, setCanonicalId] = useState(() => sugerirCanonico(grupo))

  const mesclar = useMutation({
    mutationFn: () => clientesApi.mesclarClientes(grupo.membros.map((m) => m.id), canonicalId),
    onSuccess: onMesclado,
  })

  const erro = mesclar.error
    ? ((mesclar.error as any)?.response?.data?.detail ?? 'Erro ao mesclar. Tente novamente.')
    : null

  return (
    <div className={cs.grupo}>
      <div className={cs.grupoHead}>
        <span>{Math.round(grupo.similaridade * 100)}% parecidos — escolha qual linha fica (as outras são apagadas
          depois de mover processos/contratos/tarefas/etc. para ela):</span>
      </div>
      {grupo.membros.map((m) => (
        <label key={m.id} className={cs.membro}>
          <input type="radio" name={`canon-${grupo.membros[0].id}`}
            checked={canonicalId === m.id} onChange={() => setCanonicalId(m.id)} />
          <strong>{m.nome}</strong>
          <span className={cs.membroMeta}>({m.tipo})</span>
          {m.drive_folder_id
            ? <span className={cs.membroMeta}>📁 tem pasta no Drive</span>
            : <span className={cs.semPasta}>sem pasta no Drive</span>}
          <span className={cs.membroMeta}>cadastrado em {fmtData(m.created_at)}</span>
        </label>
      ))}
      {erro && <p className={cs.erro}>⚠ {String(erro)}</p>}
      <div className={cs.acoes}>
        <button className={cs.btnMesclar} disabled={mesclar.isPending} onClick={() => mesclar.mutate()}>
          {mesclar.isPending ? 'Mesclando…' : `Mesclar em "${grupo.membros.find((m) => m.id === canonicalId)?.nome}"`}
        </button>
      </div>
    </div>
  )
}

export default function DuplicatasClientes() {
  const qc = useQueryClient()
  const [aberto, setAberto] = useState(true)

  const { data: duplicatas = [] } = useQuery({
    queryKey: ['clientes-duplicatas-cadastro'],
    queryFn: clientesApi.duplicatasCadastro,
    refetchInterval: 5 * 60_000,
  })

  if (duplicatas.length === 0) return null

  function onMesclado() {
    qc.invalidateQueries({ queryKey: ['clientes-duplicatas-cadastro'] })
    qc.invalidateQueries({ queryKey: ['clientes'] })
  }

  return (
    <div className={cs.wrap}>
      <button className={cs.header} onClick={() => setAberto((a) => !a)}>
        <span>⚠ Possíveis clientes cadastrados em duplicidade</span>
        <span className={cs.badge}>{duplicatas.length}</span>
        <span className={cs.chevron}>{aberto ? '▾' : '▸'}</span>
      </button>
      {aberto && (
        <div className={cs.lista}>
          {duplicatas.map((grupo) => (
            <GrupoDuplicata key={grupo.membros.map((m) => m.id).join('-')} grupo={grupo} onMesclado={onMesclado} />
          ))}
        </div>
      )}
    </div>
  )
}
