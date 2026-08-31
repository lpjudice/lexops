import { useEffect, useState } from 'react'
import { contratosApi } from '../api/contratos'
import type { ContratanteDecisao, ContratanteLido, ContratoFinanceiroIA } from '../api/contratos'

interface Props {
  contratoId: string
  onClose: () => void
  onApplied: () => void
}

type Acao = 'atualizar' | 'criar' | 'ignorar'

interface DecisaoState {
  acao: Acao
  cliente_id?: string          // quando acao === 'atualizar'
  nome: string
  tipo: 'PF' | 'PJ'
  cpf_cnpj: string
  email: string
  telefone: string
  endereco: string
  estado_civil: string
  profissao: string
  diferenciador: string
}

function estadoInicial(lido: ContratanteLido): DecisaoState {
  const e = lido.extraido
  // Se houver candidato por CPF, default = atualizar esse; senão criar novo.
  const porCpf = lido.candidatos.find((c) => c.match === 'cpf')
  return {
    acao: porCpf ? 'atualizar' : 'criar',
    cliente_id: porCpf?.id,
    nome: e.nome || '',
    tipo: e.tipo === 'PJ' ? 'PJ' : 'PF',
    cpf_cnpj: e.cpf_cnpj || '',
    email: e.email || '',
    telefone: e.telefone || '',
    endereco: e.endereco || '',
    estado_civil: e.estado_civil || '',
    profissao: e.profissao || '',
    diferenciador: '',
  }
}

export default function ContratantesIAModal({ contratoId, onClose, onApplied }: Props) {
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState<string | null>(null)
  const [lidos, setLidos] = useState<ContratanteLido[]>([])
  const [decisoes, setDecisoes] = useState<DecisaoState[]>([])
  const [principalIdx, setPrincipalIdx] = useState(0)
  const [salvando, setSalvando] = useState(false)
  const [fin, setFin] = useState<ContratoFinanceiroIA>({})
  const [lancarFin, setLancarFin] = useState(false)

  useEffect(() => {
    let vivo = true
    setCarregando(true)
    setErro(null)
    contratosApi
      .lerContratantes(contratoId)
      .then((r) => {
        if (!vivo) return
        setLidos(r.contratantes)
        setDecisoes(r.contratantes.map(estadoInicial))
        setPrincipalIdx(0)
        const f = r.financeiro || {}
        setFin(f)
        // Pré-marca o lançamento se a IA achou valor fixo ou êxito.
        setLancarFin(!!(f.valor_honorarios || f.tem_exito))
      })
      .catch((e: any) => {
        if (!vivo) return
        setErro(e?.response?.data?.detail || e?.message || 'Falha ao ler o contrato com a IA.')
      })
      .finally(() => vivo && setCarregando(false))
    return () => { vivo = false }
  }, [contratoId])

  const setDec = (i: number, patch: Partial<DecisaoState>) =>
    setDecisoes((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)))

  const aplicar = async () => {
    setSalvando(true)
    setErro(null)
    try {
      const payload: ContratanteDecisao[] = decisoes.map((d, i) => ({
        acao: d.acao,
        cliente_id: d.acao === 'atualizar' ? d.cliente_id : undefined,
        nome: d.nome,
        tipo: d.tipo,
        cpf_cnpj: d.cpf_cnpj || undefined,
        email: d.email || undefined,
        telefone: d.telefone || undefined,
        endereco: d.endereco || undefined,
        estado_civil: d.estado_civil || undefined,
        profissao: d.profissao || undefined,
        diferenciador: d.diferenciador || undefined,
        principal: i === principalIdx,
      }))
      await contratosApi.aplicarContratantes(contratoId, payload, {
        lancar_financeiro: lancarFin,
        financeiro: lancarFin ? fin : undefined,
      })
      onApplied()
      onClose()
    } catch (e: any) {
      setErro(e?.response?.data?.detail || e?.message || 'Falha ao aplicar as decisões.')
    } finally {
      setSalvando(false)
    }
  }

  const ativos = decisoes.filter((d) => d.acao !== 'ignorar').length

  return (
    <div style={overlay} onMouseDown={onClose}>
      <div style={card} onMouseDown={(e) => e.stopPropagation()}>
        <div style={header}>
          <strong>🔎 Contratantes lidos pela IA</strong>
          <button style={xBtn} onClick={onClose}>×</button>
        </div>

        {carregando && <p style={{ padding: 24, textAlign: 'center' }}>⏳ Lendo o contrato com a IA…</p>}
        {erro && !carregando && (
          <div style={erroBox}>❌ {erro}</div>
        )}

        {!carregando && !erro && lidos.length > 0 && (
          <>
            <p style={hint}>
              Revise cada contratante. Para os que já têm cadastro, escolha atualizar ou criar um novo.
              {decisoes.length > 1 && ' Marque em nome de quem o contrato fica vinculado.'}
            </p>

            {lidos.map((lido, i) => {
              const d = decisoes[i]
              const temCandidatos = lido.candidatos.length > 0
              return (
                <div key={i} style={bloco}>
                  <div style={blocoTop}>
                    {decisoes.length > 1 && (
                      <label style={principalLbl} title="Contrato vinculado em nome deste contratante">
                        <input
                          type="radio"
                          name="principal"
                          checked={principalIdx === i}
                          onChange={() => setPrincipalIdx(i)}
                        />
                        Principal
                      </label>
                    )}
                    <input style={{ ...inp, flex: 1, fontWeight: 600 }} value={d.nome}
                      onChange={(e) => setDec(i, { nome: e.target.value })} placeholder="Nome / Razão social" />
                    <select style={{ ...inp, width: 70 }} value={d.tipo}
                      onChange={(e) => setDec(i, { tipo: e.target.value as 'PF' | 'PJ' })}>
                      <option value="PF">PF</option>
                      <option value="PJ">PJ</option>
                    </select>
                  </div>

                  <div style={grid2}>
                    <input style={inp} value={d.cpf_cnpj} onChange={(e) => setDec(i, { cpf_cnpj: e.target.value })} placeholder="CPF / CNPJ" />
                    <input style={inp} value={d.email} onChange={(e) => setDec(i, { email: e.target.value })} placeholder="E-mail" />
                    <input style={inp} value={d.telefone} onChange={(e) => setDec(i, { telefone: e.target.value })} placeholder="Telefone" />
                    <input style={inp} value={d.estado_civil} onChange={(e) => setDec(i, { estado_civil: e.target.value })} placeholder="Estado civil" />
                    <input style={{ ...inp, gridColumn: '1 / -1' }} value={d.endereco} onChange={(e) => setDec(i, { endereco: e.target.value })} placeholder="Endereço" />
                  </div>

                  {/* Decisão: atualizar existente x criar novo x ignorar */}
                  <div style={decRow}>
                    {lido.candidatos.map((cand) => (
                      <label key={cand.id} style={decOpt}>
                        <input type="radio" name={`acao-${i}`}
                          checked={d.acao === 'atualizar' && d.cliente_id === cand.id}
                          onChange={() => setDec(i, { acao: 'atualizar', cliente_id: cand.id })} />
                        Atualizar: <b>{cand.nome}</b>{' '}
                        <span style={tag}>{cand.match === 'cpf' ? 'mesmo CPF' : 'nome parecido'}{cand.incompleto ? ' · incompleto' : ''}</span>
                      </label>
                    ))}
                    <label style={decOpt}>
                      <input type="radio" name={`acao-${i}`}
                        checked={d.acao === 'criar'}
                        onChange={() => setDec(i, { acao: 'criar', cliente_id: undefined })} />
                      {temCandidatos ? 'Criar 2º cadastro (novo)' : 'Criar cadastro (novo, pendente de revisão)'}
                    </label>
                    <label style={decOpt}>
                      <input type="radio" name={`acao-${i}`}
                        checked={d.acao === 'ignorar'}
                        onChange={() => setDec(i, { acao: 'ignorar' })} />
                      Ignorar
                    </label>
                  </div>

                  {/* Diferenciador só quando criando novo e já existe homônimo/candidato */}
                  {d.acao === 'criar' && temCandidatos && (
                    <input style={{ ...inp, width: '100%', marginTop: 6 }}
                      value={d.diferenciador}
                      onChange={(e) => setDec(i, { diferenciador: e.target.value })}
                      placeholder="Como diferenciar dos homônimos? (ex.: cônjuge do sócio, filial SP) — vai para observações" />
                  )}
                </div>
              )
            })}

            {/* ── Financeiro (honorários) ──────────────────────────────── */}
            <div style={{ ...bloco, background: '#f9fafb' }}>
              <label style={{ ...decOpt, fontWeight: 600, marginBottom: lancarFin ? 8 : 0 }}>
                <input type="checkbox" checked={lancarFin} onChange={(e) => setLancarFin(e.target.checked)} />
                💰 Lançar honorários no financeiro
              </label>
              {lancarFin && (
                <>
                  <div style={grid2}>
                    <input style={inp} type="number" value={fin.valor_honorarios ?? ''}
                      onChange={(e) => setFin({ ...fin, valor_honorarios: e.target.value === '' ? null : Number(e.target.value) })}
                      placeholder="Valor dos honorários (R$)" />
                    <input style={inp} value={fin.data_vencimento ?? ''}
                      onChange={(e) => setFin({ ...fin, data_vencimento: e.target.value })}
                      placeholder="1º vencimento (AAAA-MM-DD)" />
                  </div>
                  <input style={{ ...inp, width: '100%', marginTop: 6 }} type="number" min={1}
                    value={fin.num_parcelas ?? ''}
                    onChange={(e) => setFin({ ...fin, num_parcelas: e.target.value === '' ? null : Number(e.target.value) })}
                    placeholder="Nº de parcelas (1 = à vista; 2+ gera cronograma mensal)" />
                  <label style={{ ...decOpt, marginTop: 6 }}>
                    <input type="checkbox" checked={!!fin.tem_exito}
                      onChange={(e) => setFin({ ...fin, tem_exito: e.target.checked })} />
                    Tem honorários de êxito
                  </label>
                  {fin.tem_exito && (
                    <div style={grid2}>
                      <input style={inp} type="number" value={fin.percentual_exito ?? ''}
                        onChange={(e) => setFin({ ...fin, percentual_exito: e.target.value === '' ? null : Number(e.target.value) })}
                        placeholder="% de êxito" />
                      <input style={inp} type="number" value={fin.valor_causa ?? ''}
                        onChange={(e) => setFin({ ...fin, valor_causa: e.target.value === '' ? null : Number(e.target.value) })}
                        placeholder="Valor da causa (R$)" />
                    </div>
                  )}
                  <input style={{ ...inp, width: '100%', marginTop: 6 }} value={fin.condicao_pagamento ?? ''}
                    onChange={(e) => setFin({ ...fin, condicao_pagamento: e.target.value })}
                    placeholder="Condição de pagamento (ex.: parcela única, 3x)" />
                </>
              )}
            </div>

            <div style={footer}>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{ativos} contratante(s) a aplicar</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={btnGhost} onClick={onClose} disabled={salvando}>Cancelar</button>
                <button style={btnPrimary} onClick={aplicar} disabled={salvando || ativos === 0}>
                  {salvando ? '⏳ Aplicando…' : 'Aplicar ao cadastro'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── estilos inline ────────────────────────────────────────────────────────────
const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '5vh 16px', overflowY: 'auto',
}
const card: React.CSSProperties = {
  background: '#fff', borderRadius: 12, width: 'min(720px, 100%)', boxShadow: '0 10px 40px rgba(0,0,0,.25)',
}
const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '14px 18px', borderBottom: '1px solid #eee',
}
const xBtn: React.CSSProperties = { border: 'none', background: 'none', fontSize: 22, cursor: 'pointer', color: '#9ca3af' }
const hint: React.CSSProperties = { padding: '10px 18px 0', fontSize: 13, color: '#6b7280', margin: 0 }
const bloco: React.CSSProperties = { margin: '12px 18px', padding: 12, border: '1px solid #e5e7eb', borderRadius: 10 }
const blocoTop: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }
const principalLbl: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#374151', whiteSpace: 'nowrap' }
const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }
const decRow: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }
const decOpt: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#374151' }
const tag: React.CSSProperties = { fontSize: 11, color: '#6b7280', background: '#f3f4f6', borderRadius: 6, padding: '1px 6px' }
const inp: React.CSSProperties = { padding: '7px 9px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13 }
const footer: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '12px 18px', borderTop: '1px solid #eee', position: 'sticky', bottom: 0, background: '#fff',
}
const erroBox: React.CSSProperties = { margin: 18, padding: 12, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, color: '#b91c1c', fontSize: 13 }
const btnPrimary: React.CSSProperties = { padding: '8px 16px', border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer' }
const btnGhost: React.CSSProperties = { padding: '8px 16px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer' }
