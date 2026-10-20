/**
 * Seção "Responsáveis e escopo" do card do contrato/procuração: quem da equipe é
 * responsável, o escopo/recomendações, edição inline e o botão que (re)envia o
 * aviso por e-mail + Telegram. O aviso nunca leva dado financeiro (ver
 * app/services/contrato_notificacao.py).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { contratosApi } from '../api/contratos'
import type { Contrato, ResultadoNotificacao } from '../api/contratos'
import { responsaveisApi } from '../api/responsaveis'
import ResponsaveisMulti from './ResponsaveisMulti'
import EscopoEditor from './EscopoEditor'

const STATUS_EMAIL: Record<string, string> = { enviado: 'e-mail enviado', sem_email: 'sem e-mail cadastrado' }
const STATUS_TG: Record<string, string> = {
  enviado: 'Telegram enviado', nao_vinculado: 'Telegram não vinculado', falhou: 'Telegram falhou',
}

function resumo(r: ResultadoNotificacao): { texto: string; ok: boolean } {
  const email = r.email.startsWith('erro') ? `e-mail falhou (${r.email.replace(/^erro:\s*/, '')})` : STATUS_EMAIL[r.email] ?? r.email
  const tg = STATUS_TG[r.telegram] ?? r.telegram
  return { texto: `${email} · ${tg}`, ok: r.email === 'enviado' || r.telegram === 'enviado' }
}

const botao: React.CSSProperties = {
  padding: '5px 12px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb',
  background: '#fff', cursor: 'pointer', color: '#374151', fontWeight: 600,
}

export default function ContratoResponsaveisEscopo({ contrato }: { contrato: Contrato }) {
  const qc = useQueryClient()
  const [editando, setEditando] = useState(false)
  const [ids, setIds] = useState<string[]>(contrato.responsaveis_ids ?? [])
  const [escopo, setEscopo] = useState(contrato.escopo_recomendacoes ?? '')
  const [resultados, setResultados] = useState<ResultadoNotificacao[] | null>(null)

  const { data: responsaveis = [] } = useQuery({
    queryKey: ['responsaveis'],
    queryFn: () => responsaveisApi.listar(),
    staleTime: 30_000,
  })
  const nomePorId = new Map(responsaveis.map((r) => [r.id, r.nome]))

  const salvar = useMutation({
    mutationFn: () => contratosApi.atualizar(contrato.id, { responsaveis_ids: ids, escopo_recomendacoes: escopo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setEditando(false)
    },
    onError: (e: any) => alert(`Erro ao salvar:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const notificar = useMutation({
    mutationFn: () => contratosApi.notificarResponsaveis(contrato.id),
    onSuccess: (r) => {
      setResultados(r.resultados)
      qc.invalidateQueries({ queryKey: ['contratos'] })
    },
    onError: (e: any) => alert(`Erro ao notificar:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const abrirEdicao = () => {
    setIds(contrato.responsaveis_ids ?? [])
    setEscopo(contrato.escopo_recomendacoes ?? '')
    setEditando(true)
  }

  const salvos = contrato.responsaveis_ids ?? []
  const quando = contrato.responsaveis_notificados_em
    ? new Date(contrato.responsaveis_notificados_em).toLocaleString('pt-BR') : null

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 14, marginBottom: 14, background: '#fcfcfc' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: '#1d1e20' }}>Responsáveis e escopo</span>
        <div style={{ display: 'flex', gap: 6 }}>
          {!editando && (
            <button type="button" style={botao} onClick={abrirEdicao}>✎ Editar</button>
          )}
          {!editando && salvos.length > 0 && (
            <button type="button" style={{ ...botao, background: '#ecfdf5', borderColor: '#a7f3d0', color: '#065f46' }}
              disabled={notificar.isPending}
              title="Envia e-mail (e Telegram, pra quem vinculou) com escopo, recomendações e o link da pasta do cliente — sem dados financeiros"
              onClick={() => { if (confirm('Enviar o aviso aos responsáveis agora?')) notificar.mutate() }}>
              {notificar.isPending ? '⏳ Enviando...' : quando ? '🔔 Reenviar aviso' : '🔔 Notificar responsáveis'}
            </button>
          )}
        </div>
      </div>

      {editando ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Responsáveis pelo contrato/cliente</div>
            <ResponsaveisMulti value={ids} onChange={setIds} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Escopo e recomendações</div>
            <EscopoEditor value={escopo} onChange={setEscopo} />
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" style={{ ...botao, background: '#0d9488', borderColor: '#0d9488', color: '#fff' }}
              disabled={salvar.isPending} onClick={() => salvar.mutate()}>
              {salvar.isPending ? 'Salvando...' : 'Salvar'}
            </button>
            <button type="button" style={botao} onClick={() => setEditando(false)}>Cancelar</button>
          </div>
        </div>
      ) : (
        <>
          {salvos.length === 0 ? (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>Nenhum responsável selecionado.</div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {salvos.map((id) => (
                <span key={id} style={{ padding: '3px 10px', borderRadius: 999, background: '#ecfdf5', border: '1px solid #a7f3d0', fontSize: 12, color: '#065f46' }}>
                  {nomePorId.get(id) ?? 'Responsável removido'}
                </span>
              ))}
            </div>
          )}
          {contrato.escopo_recomendacoes?.trim() ? (
            <div style={{ fontSize: 13, color: '#374151', whiteSpace: 'pre-wrap', lineHeight: 1.55 }}>
              {contrato.escopo_recomendacoes}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>Sem escopo/recomendações.</div>
          )}
          {quando && (
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>Último aviso enviado em {quando}</div>
          )}
          {resultados && (
            <div style={{ marginTop: 8, fontSize: 12, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {resultados.map((r, i) => {
                const { texto, ok } = resumo(r)
                return (
                  <div key={i} style={{ color: ok ? '#065f46' : '#b45309' }}>
                    {ok ? '✓' : '⚠'} <b>{r.responsavel}</b> — {texto}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
