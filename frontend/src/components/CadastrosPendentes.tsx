import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cadastroSubmissoesApi } from '../api/clientes'
import type { CadastroSubmissaoDetalhe } from '../api/clientes'
import cs from './CadastrosPendentes.module.css'

const LABELS: Record<string, string> = {
  nome: 'Nome / Razão social',
  nome_fantasia: 'Nome fantasia',
  cpf_cnpj: 'CPF / CNPJ',
  rg: 'RG',
  data_nascimento: 'Data de nascimento',
  estado_civil: 'Estado civil',
  profissao: 'Profissão',
  email: 'E-mail',
  telefone: 'Telefone',
  whatsapp: 'WhatsApp',
  cep: 'CEP',
  logradouro: 'Logradouro',
  numero: 'Número',
  complemento: 'Complemento',
  bairro: 'Bairro',
  cidade: 'Cidade',
  uf: 'UF',
  empresas_vinculadas: 'Empresas vinculadas',
  responsavel_nome: 'Responsável',
  responsavel_cpf: 'CPF do responsável',
  responsavel_email: 'E-mail do responsável',
  responsavel_telefone: 'Telefone do responsável',
  observacoes: 'Observações',
}

function fmtData(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleString('pt-BR')
}

export default function CadastrosPendentes() {
  const qc = useQueryClient()
  const [aberto, setAberto] = useState(true)
  const [revisandoId, setRevisandoId] = useState<string | null>(null)

  const { data: pendentes = [] } = useQuery({
    queryKey: ['cadastro-submissoes', 'pendente'],
    queryFn: () => cadastroSubmissoesApi.listar('pendente'),
    refetchInterval: 30000,
  })

  if (pendentes.length === 0) return null

  return (
    <div className={cs.wrap}>
      <button className={cs.header} onClick={() => setAberto((a) => !a)}>
        <span>📥 Cadastros pendentes de revisão</span>
        <span className={cs.badge}>{pendentes.length}</span>
        <span className={cs.chevron}>{aberto ? '▾' : '▸'}</span>
      </button>

      {aberto && (
        <div className={cs.lista}>
          {pendentes.map((s) => (
            <div key={s.id} className={cs.item}>
              <div className={cs.itemInfo}>
                <span className={cs.tipo}>{s.tipo}</span>
                <strong>{s.nome_enviado || '(sem nome)'}</strong>
                <span className={s.is_update ? cs.tagUpdate : cs.tagNovo}>
                  {s.is_update ? `atualização · ${s.cliente_alvo_nome ?? ''}` : 'cliente novo'}
                </span>
                {s.qtd_anexos > 0 && <span className={cs.meta}>📎 {s.qtd_anexos}</span>}
                <span className={cs.meta}>{fmtData(s.created_at)}</span>
              </div>
              <button className={cs.btnRevisar} onClick={() => setRevisandoId(s.id)}>Revisar</button>
            </div>
          ))}
        </div>
      )}

      {revisandoId && (
        <RevisaoModal
          id={revisandoId}
          onClose={() => setRevisandoId(null)}
          onDone={() => {
            setRevisandoId(null)
            qc.invalidateQueries({ queryKey: ['cadastro-submissoes'] })
            qc.invalidateQueries({ queryKey: ['clientes'] })
          }}
        />
      )}
    </div>
  )
}

function RevisaoModal({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const { data: sub, isLoading } = useQuery({
    queryKey: ['cadastro-submissao', id],
    queryFn: () => cadastroSubmissoesApi.obter(id),
  })

  const [selecionados, setSelecionados] = useState<Set<string> | null>(null)

  // Inicializa a seleção com os campos que mudaram (uma vez, quando carrega).
  const selecao = useMemo<Set<string>>(() => {
    if (selecionados) return selecionados
    if (!sub) return new Set()
    return new Set(sub.diff.filter((d) => d.mudou).map((d) => d.campo))
  }, [sub, selecionados])

  const aprovar = useMutation({
    mutationFn: (s: CadastroSubmissaoDetalhe) =>
      cadastroSubmissoesApi.aprovar(s.id, Array.from(selecao)),
    onSuccess: onDone,
  })
  const rejeitar = useMutation({
    mutationFn: () => cadastroSubmissoesApi.rejeitar(id),
    onSuccess: onDone,
  })

  const toggle = (campo: string) => {
    const novo = new Set(selecao)
    novo.has(campo) ? novo.delete(campo) : novo.add(campo)
    setSelecionados(novo)
  }

  return (
    <div className={cs.overlay} onClick={onClose}>
      <div className={cs.modal} onClick={(e) => e.stopPropagation()}>
        {isLoading || !sub ? (
          <p className={cs.muted}>Carregando…</p>
        ) : (
          <>
            <div className={cs.modalHead}>
              <div>
                <h2 className={cs.modalTitulo}>{sub.nome_enviado || '(sem nome)'}</h2>
                <p className={cs.muted}>
                  {sub.tipo} · {sub.is_update ? `atualização de ${sub.cliente_alvo_nome ?? ''}` : 'cliente novo'}
                  {' · '}enviado {fmtData(sub.created_at)}
                </p>
              </div>
              <button className={cs.fechar} onClick={onClose}>×</button>
            </div>

            <p className={cs.instrucao}>
              Marque os campos que deseja aplicar. Realçados = mudaram em relação ao cadastro atual.
            </p>

            <div className={cs.tabela}>
              <div className={cs.thead}>
                <span></span><span>Campo</span><span>Atual</span><span>Enviado</span>
              </div>
              {sub.diff.map((d) => (
                <label key={d.campo} className={`${cs.linha} ${d.mudou ? cs.linhaMudou : ''}`}>
                  <input type="checkbox" checked={selecao.has(d.campo)} onChange={() => toggle(d.campo)} />
                  <span className={cs.campo}>{LABELS[d.campo] ?? d.campo}</span>
                  <span className={cs.atual}>{d.atual || '—'}</span>
                  <span className={cs.novo}>{d.novo || '—'}</span>
                </label>
              ))}
            </div>

            {sub.anexos.length > 0 && (
              <p className={cs.anexos}>
                📎 {sub.anexos.length} anexo(s): {sub.anexos.map((a) => a.filename).join(', ')}
                <span className={cs.muted}> — vão pro Drive do cliente na aprovação.</span>
              </p>
            )}

            {sub.consentimento_texto && (
              <p className={cs.consent}>
                ✔ Consentimento LGPD em {fmtData(sub.consentimento_em)} (IP {sub.ip || '—'})
              </p>
            )}

            {(aprovar.isError || rejeitar.isError) && (
              <p className={cs.erro}>⚠ Erro ao processar. Tente novamente.</p>
            )}

            <div className={cs.acoes}>
              <button className={cs.btnRejeitar} disabled={rejeitar.isPending}
                onClick={() => rejeitar.mutate()}>
                {rejeitar.isPending ? '…' : 'Rejeitar'}
              </button>
              <button className={cs.btnAprovar} disabled={aprovar.isPending || selecao.size === 0}
                onClick={() => aprovar.mutate(sub)}>
                {aprovar.isPending ? 'Aplicando…' : `Aprovar (${selecao.size})`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
