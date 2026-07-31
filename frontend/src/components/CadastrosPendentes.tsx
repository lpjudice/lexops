import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cadastroSubmissoesApi, clientesApi } from '../api/clientes'
import {
  applyDocMask, brParaIso, ESTADO_CIVIL_OPCOES, isoParaBr,
  maskCEP, maskCPF, maskDataBr, maskTelefone,
} from '../utils/masks'
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

type Tipo = 'PF' | 'PJ'

// Ordem de exibição dos campos editáveis por tipo.
const CAMPOS_TIPO: Record<Tipo, string[]> = {
  PF: ['nome', 'cpf_cnpj', 'rg', 'data_nascimento', 'estado_civil', 'profissao',
    'email', 'telefone', 'whatsapp',
    'cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf',
    'empresas_vinculadas', 'observacoes'],
  PJ: ['nome', 'nome_fantasia', 'cpf_cnpj', 'email', 'telefone', 'whatsapp',
    'cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf',
    'responsavel_nome', 'responsavel_cpf', 'responsavel_email', 'responsavel_telefone',
    'observacoes'],
}

function labelCampo(campo: string, tipo: Tipo): string {
  if (campo === 'nome') return tipo === 'PF' ? 'Nome completo' : 'Razão social'
  if (campo === 'cpf_cnpj') return tipo === 'PF' ? 'CPF' : 'CNPJ'
  return LABELS[campo] ?? campo
}

function RevisaoModal({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const { data: sub, isLoading } = useQuery({
    queryKey: ['cadastro-submissao', id],
    queryFn: () => cadastroSubmissoesApi.obter(id),
  })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: clientesApi.listar })

  const [tipo, setTipo] = useState<Tipo | null>(null)
  const [destino, setDestino] = useState<string>('') // 'novo' | cliente_id
  const [campos, setCampos] = useState<Record<string, string> | null>(null)

  // Pré-preenche quando a submissão carrega (data em DD/MM/AAAA para edição).
  useEffect(() => {
    if (!sub) return
    setTipo((t) => t ?? sub.tipo)
    setDestino((d) => d || (sub.cliente_alvo_id ?? 'novo'))
    setCampos((c) => c ?? { ...sub.dados, data_nascimento: isoParaBr(sub.dados?.data_nascimento) })
  }, [sub])

  const aprovar = useMutation({
    mutationFn: () => cadastroSubmissoesApi.aprovar(id, {
      tipo: tipo!,
      criar_novo: destino === 'novo',
      cliente_id_alvo: destino === 'novo' ? null : destino,
      dados: { ...(campos ?? {}), data_nascimento: brParaIso(campos?.data_nascimento) },
    }),
    onSuccess: onDone,
  })
  const rejeitar = useMutation({ mutationFn: () => cadastroSubmissoesApi.rejeitar(id), onSuccess: onDone })

  const set = (campo: string, valor: string) => setCampos((c) => ({ ...(c ?? {}), [campo]: valor }))

  function inputPara(campo: string, t: Tipo) {
    const v = campos?.[campo] ?? ''
    if (campo === 'estado_civil') {
      return (
        <select className={cs.campoInput} value={v} onChange={(e) => set(campo, e.target.value)}>
          <option value="">—</option>
          {ESTADO_CIVIL_OPCOES.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      )
    }
    if (campo === 'data_nascimento') {
      return <input className={cs.campoInput} placeholder="DD/MM/AAAA" inputMode="numeric" maxLength={10}
        value={v} onChange={(e) => set(campo, maskDataBr(e.target.value))} />
    }
    if (campo === 'observacoes' || campo === 'empresas_vinculadas') {
      return <textarea className={cs.campoInput} rows={2} value={v} onChange={(e) => set(campo, e.target.value)} />
    }
    const mask =
      campo === 'cpf_cnpj' ? (val: string) => applyDocMask(val, t) :
      campo === 'responsavel_cpf' ? maskCPF :
      (campo === 'telefone' || campo === 'whatsapp' || campo === 'responsavel_telefone') ? maskTelefone :
      campo === 'cep' ? maskCEP :
      (val: string) => val
    return <input className={cs.campoInput} value={v} onChange={(e) => set(campo, mask(e.target.value))} />
  }

  const pronto = !isLoading && sub && tipo && campos

  return (
    <div className={cs.overlay} onClick={onClose}>
      <div className={cs.modal} onClick={(e) => e.stopPropagation()}>
        {!pronto ? (
          <p className={cs.muted}>Carregando…</p>
        ) : (
          <>
            <div className={cs.modalHead}>
              <div>
                <h2 className={cs.modalTitulo}>Revisar cadastro</h2>
                <p className={cs.muted}>
                  Enviado {fmtData(sub.created_at)}
                  {sub.qtd_anexos > 0 ? ` · 📎 ${sub.qtd_anexos} anexo(s)` : ''}
                </p>
              </div>
              <button className={cs.fechar} onClick={onClose}>×</button>
            </div>

            <p className={cs.instrucao}>
              Confira e corrija os dados, escolha o tipo e o destino, e aprove.
            </p>

            {/* Tipo */}
            <div className={cs.tipoRow}>
              {(['PF', 'PJ'] as Tipo[]).map((t) => (
                <button key={t} type="button"
                  className={tipo === t ? cs.tipoAtivo : cs.tipoBtn}
                  onClick={() => setTipo(t)}>
                  {t === 'PF' ? 'Pessoa Física' : 'Pessoa Jurídica'}
                </button>
              ))}
            </div>

            {/* Destino */}
            <label className={cs.campoLinha}>
              <span className={cs.campoLabel}>Destino</span>
              <select className={cs.campoInput} value={destino} onChange={(e) => setDestino(e.target.value)}>
                <option value="novo">➕ Criar cliente novo</option>
                {clientes.map((c) => (
                  <option key={c.id} value={c.id}>{c.nome} ({c.tipo})</option>
                ))}
              </select>
            </label>

            {/* Campos editáveis */}
            {CAMPOS_TIPO[tipo].map((campo) => (
              <label key={campo} className={cs.campoLinha}>
                <span className={cs.campoLabel}>{labelCampo(campo, tipo)}</span>
                {inputPara(campo, tipo)}
              </label>
            ))}

            {sub.anexos.length > 0 && (
              <p className={cs.anexos}>
                📎 {sub.anexos.map((a) => a.filename).join(', ')}
                <span className={cs.muted}> — vão pro Drive na aprovação.</span>
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
              <button className={cs.btnAprovar} disabled={aprovar.isPending || !(campos?.nome ?? '').trim()}
                onClick={() => aprovar.mutate()}>
                {aprovar.isPending ? 'Aplicando…' : destino === 'novo' ? 'Aprovar e criar' : 'Aprovar e atualizar'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
