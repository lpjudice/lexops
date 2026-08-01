import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  patrimonioApi,
  type Bem,
  type BemCreate,
  type CadeiaElo,
  type ObjetivoBem,
  type Socio,
  type StatusBem,
  type TipoBem,
  type TipoDocumentoElo,
} from '../api/patrimonio'
import styles from '../pages/Page.module.css'
import s from './PatrimonioSection.module.css'

const STATUS_LABEL: Record<StatusBem, string> = {
  em_validacao: 'Em validação',
  validado: 'Validado',
  incerto: 'Incerto',
}
const STATUS_ORDER: StatusBem[] = ['em_validacao', 'validado', 'incerto']

const OBJETIVO_LABEL: Record<ObjetivoBem, string> = {
  venda: 'Venda', aluguel: 'Aluguel', segurar: 'Segurar',
}

const TIPO_DOC_LABEL: Record<TipoDocumentoElo, string> = {
  contrato_compra_venda: 'Contrato de compra e venda',
  escritura_publica: 'Escritura pública',
  cessao_direitos: 'Cessão de direitos',
  matricula: 'Matrícula / Registro',
  formal_partilha: 'Formal de partilha',
  outro: 'Outro documento',
}

function brl(n?: number | null) {
  if (n == null) return '—'
  return Number(n).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}
function norm(x?: string | null) {
  return (x || '').trim().toLowerCase().replace(/\s+/g, ' ')
}
function baixarBlob(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nome
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Datas: guardadas internamente em ISO (YYYY-MM-DD), exibidas/digitadas em DD/MM/AAAA.
function isoToBr(iso?: string | null): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return y && m && d ? `${d}/${m}/${y}` : ''
}
function brToIso(br: string): string {
  const m = br.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  return m ? `${m[3]}-${m[2]}-${m[1]}` : ''
}

/** Campo de data em DD/MM/AAAA que emite ISO (ou '' se incompleto). */
function DateInput({ value, onChange, className }: {
  value?: string | null; onChange: (iso: string) => void; className?: string
}) {
  const [txt, setTxt] = useState(isoToBr(value))
  useEffect(() => { setTxt(isoToBr(value)) }, [value])
  const handle = (raw: string) => {
    const d = raw.replace(/\D/g, '').slice(0, 8)
    const out = d.length > 4 ? `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`
      : d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d
    setTxt(out)
    onChange(brToIso(out))
  }
  return (
    <input type="text" inputMode="numeric" placeholder="DD/MM/AAAA" maxLength={10}
      className={className} value={txt} onChange={(e) => handle(e.target.value)} />
  )
}

// ── Form de bem (criar/editar) ───────────────────────────────────────────────
type FormState = Omit<BemCreate, 'cliente_id' | 'nome'> & { nome: string }

function emptyForm(): FormState {
  return {
    tipo_bem: 'imovel', nome: '', descricao: '',
    valor_compra: undefined, valor_mercado: undefined, valor_ir: undefined,
    data_compra: '', objetivo: undefined,
    descricao_matricula: '', numero_matricula: '', cartorio: '',
    status: 'em_validacao', integralizar_holding: false,
    proprietario_real: '', proprietario_matricula: '',
    tem_gravame: false, gravame_descricao: '', observacoes: '',
    empresa_nome: '', empresa_cnpj: '', capital_social: undefined,
    valor_balanco: undefined, data_balanco: '',
  }
}

function BemForm({
  initial, saving, onCancel, onSave,
}: {
  initial: FormState
  saving: boolean
  onCancel: () => void
  onSave: (data: FormState) => void
}) {
  const [f, setF] = useState<FormState>(initial)
  const isImovel = f.tipo_bem === 'imovel'
  const set = (patch: Partial<FormState>) => setF({ ...f, ...patch })
  const num = (v: string) => (v === '' ? undefined : parseFloat(v))

  return (
    <form
      className={styles.form}
      onSubmit={(e) => { e.preventDefault(); onSave(f) }}
    >
      <div className={s.grid}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Tipo do bem</label>
          <select className={styles.input} value={f.tipo_bem}
            onChange={(e) => set({ tipo_bem: e.target.value as TipoBem })}>
            <option value="imovel">Imóvel</option>
            <option value="movel">Móvel</option>
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Nome do bem *</label>
          <input className={styles.input} required value={f.nome}
            onChange={(e) => set({ nome: e.target.value })} placeholder="Ex.: Apartamento Rua X, 100" />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Objetivo</label>
          <select className={styles.input} value={f.objetivo ?? ''}
            onChange={(e) => set({ objetivo: (e.target.value || undefined) as ObjetivoBem | undefined })}>
            <option value="">—</option>
            <option value="venda">Venda</option>
            <option value="aluguel">Aluguel</option>
            <option value="segurar">Segurar</option>
          </select>
        </div>
      </div>

      <div className={styles.formRow}>
        <label className={styles.formLabel}>Descrição</label>
        <textarea className={styles.input} rows={2} value={f.descricao ?? ''}
          onChange={(e) => set({ descricao: e.target.value })} />
      </div>

      <div className={s.grid}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Valor de compra</label>
          <input type="number" step="0.01" min="0" className={styles.input}
            value={f.valor_compra ?? ''} onChange={(e) => set({ valor_compra: num(e.target.value) })} />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Valor de mercado (atual)</label>
          <input type="number" step="0.01" min="0" className={styles.input}
            value={f.valor_mercado ?? ''} onChange={(e) => set({ valor_mercado: num(e.target.value) })} />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Valor no IR</label>
          <input type="number" step="0.01" min="0" className={styles.input}
            value={f.valor_ir ?? ''} onChange={(e) => set({ valor_ir: num(e.target.value) })} />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Data da compra</label>
          <DateInput className={styles.input} value={f.data_compra}
            onChange={(iso) => set({ data_compra: iso })} />
        </div>
      </div>

      {isImovel && (
        <>
          <div className={s.grid}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Nº da matrícula</label>
              <input className={styles.input} value={f.numero_matricula ?? ''}
                onChange={(e) => set({ numero_matricula: e.target.value })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Cartório</label>
              <input className={styles.input} value={f.cartorio ?? ''}
                onChange={(e) => set({ cartorio: e.target.value })} />
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição conforme matrícula</label>
            <textarea className={styles.input} rows={2} value={f.descricao_matricula ?? ''}
              onChange={(e) => set({ descricao_matricula: e.target.value })} />
          </div>
        </>
      )}

      {!isImovel && (
        <div className={s.cotaBox}>
          <div className={s.cotaTitle}>🏢 Cota social / participação societária (opcional)</div>
          <div className={s.grid}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Nome da empresa</label>
              <input className={styles.input} value={f.empresa_nome ?? ''}
                onChange={(e) => set({ empresa_nome: e.target.value })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>CNPJ</label>
              <input className={styles.input} value={f.empresa_cnpj ?? ''}
                onChange={(e) => set({ empresa_cnpj: e.target.value })} placeholder="00.000.000/0001-00" />
            </div>
          </div>
          <div className={s.grid}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Capital social</label>
              <input type="number" step="0.01" min="0" className={styles.input}
                value={f.capital_social ?? ''} onChange={(e) => set({ capital_social: num(e.target.value) })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Valor do balanço (PL)</label>
              <input type="number" step="0.01" min="0" className={styles.input}
                value={f.valor_balanco ?? ''} onChange={(e) => set({ valor_balanco: num(e.target.value) })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Data do balanço</label>
              <DateInput className={styles.input} value={f.data_balanco}
                onChange={(iso) => set({ data_balanco: iso })} />
            </div>
          </div>
          <p className={s.cotaHint}>
            O quadro de sócios (nome, CPF, %, integralização) e o anexo do balanço
            são gerenciados no card do bem após salvar.
          </p>
        </div>
      )}

      <div className={s.grid}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Proprietário real</label>
          <input className={styles.input} value={f.proprietario_real ?? ''}
            onChange={(e) => set({ proprietario_real: e.target.value })} />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Proprietário na matrícula</label>
          <input className={styles.input} value={f.proprietario_matricula ?? ''}
            onChange={(e) => set({ proprietario_matricula: e.target.value })} />
        </div>
      </div>

      <div className={s.grid}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Status</label>
          <select className={styles.input} value={f.status}
            onChange={(e) => set({ status: e.target.value as StatusBem })}>
            {STATUS_ORDER.map((st) => <option key={st} value={st}>{STATUS_LABEL[st]}</option>)}
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>&nbsp;</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={!!f.integralizar_holding}
              onChange={(e) => set({ integralizar_holding: e.target.checked })} />
            Integralizar na holding
          </label>
        </div>
      </div>

      <div className={styles.formRow}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
          <input type="checkbox" checked={!!f.tem_gravame}
            onChange={(e) => set({ tem_gravame: e.target.checked })} />
          Possui hipoteca ou outro gravame na matrícula
        </label>
      </div>
      {f.tem_gravame && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Qual gravame / detalhes</label>
          <textarea className={styles.input} rows={2} value={f.gravame_descricao ?? ''}
            onChange={(e) => set({ gravame_descricao: e.target.value })} />
        </div>
      )}

      <div className={styles.formRow}>
        <label className={styles.formLabel}>Observações gerais</label>
        <textarea className={styles.input} rows={2} value={f.observacoes ?? ''}
          onChange={(e) => set({ observacoes: e.target.value })} />
      </div>

      <div className={s.rowBtns}>
        <button type="submit" className={styles.btnPrimary} disabled={saving || !f.nome}>
          {saving ? 'Salvando...' : 'Salvar bem'}
        </button>
        <button type="button" className={styles.btnTable} onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  )
}

// ── Cadeia sucessória ─────────────────────────────────────────────────────────
function CadeiaSection({ bem }: { bem: Bem }) {
  const qc = useQueryClient()
  const [aberto, setAberto] = useState((bem.cadeia?.length ?? 0) > 0)
  const [novoAberto, setNovoAberto] = useState(false)
  const eloFileRef = useRef<Record<string, HTMLInputElement | null>>({})
  const invalidate = () => qc.invalidateQueries({ queryKey: ['patrimonio', bem.cliente_id] })

  const [nf, setNf] = useState<{ tipo_documento: TipoDocumentoElo; de_quem: string; para_quem: string; data: string; descricao: string }>(
    { tipo_documento: 'contrato_compra_venda', de_quem: '', para_quem: '', data: '', descricao: '' }
  )

  const criar = useMutation({
    mutationFn: () => patrimonioApi.criarElo(bem.id, {
      ...nf, data: nf.data || undefined, ordem: bem.cadeia?.length ?? 0,
    }),
    onSuccess: () => {
      invalidate()
      setNovoAberto(false)
      setNf({ tipo_documento: 'contrato_compra_venda', de_quem: '', para_quem: '', data: '', descricao: '' })
    },
  })
  const deletar = useMutation({
    mutationFn: (eloId: string) => patrimonioApi.deletarElo(bem.id, eloId),
    onSuccess: invalidate,
  })
  const uploadElo = useMutation({
    mutationFn: ({ eloId, file }: { eloId: string; file: File }) => patrimonioApi.uploadAnexoElo(bem.id, eloId, file),
    onSuccess: invalidate,
  })

  return (
    <div>
      <button className={s.cadeiaToggle} onClick={() => setAberto(!aberto)}>
        <span>{aberto ? '▾' : '▸'}</span>
        🔗 Cadeia sucessória do imóvel
        <span style={{ color: 'var(--gray-mid)', fontWeight: 600 }}>
          ({bem.cadeia?.length ?? 0} elo{(bem.cadeia?.length ?? 0) === 1 ? '' : 's'})
        </span>
      </button>

      {aberto && (
        <>
          {(bem.cadeia?.length ?? 0) === 0 ? (
            <p className={styles.empty} style={{ marginTop: 8 }}>
              Nenhum elo cadastrado. Use quando a matrícula ainda não está no nome do cliente
              (ex.: contrato de compra e venda → escritura pública → cessão).
            </p>
          ) : (
            <div className={s.cadeiaChain}>
              {bem.cadeia.map((elo: CadeiaElo) => (
                <div key={elo.id} className={s.elo}>
                  <div className={s.eloDot} />
                  <div className={s.eloCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div className={s.eloTipo}>{TIPO_DOC_LABEL[elo.tipo_documento]}</div>
                      <button className={s.anexoDel} title="Remover elo"
                        onClick={() => { if (confirm('Remover este elo da cadeia?')) deletar.mutate(elo.id) }}>×</button>
                    </div>
                    {(elo.de_quem || elo.para_quem) && (
                      <div className={s.eloParties}>
                        {elo.de_quem || '—'} <span style={{ color: 'var(--teal)' }}>→</span> {elo.para_quem || '—'}
                        {elo.data && <> · {fmtDate(elo.data)}</>}
                      </div>
                    )}
                    {elo.descricao && <div className={s.eloDesc}>{elo.descricao}</div>}
                    <div className={s.eloActions}>
                      {elo.drive_link ? (
                        <a className={s.anexoLink} href={elo.drive_link} target="_blank" rel="noreferrer">
                          📎 {elo.arquivo_nome || 'documento'} ↗
                        </a>
                      ) : (
                        <>
                          <label className={s.uploadBtn} style={{ padding: '4px 10px' }}>
                            📎 Anexar documento
                            <input type="file" style={{ display: 'none' }}
                              ref={(el) => { eloFileRef.current[elo.id] = el }}
                              onChange={(e) => {
                                const file = e.target.files?.[0]
                                if (file) uploadElo.mutate({ eloId: elo.id, file })
                                if (eloFileRef.current[elo.id]) eloFileRef.current[elo.id]!.value = ''
                              }} />
                          </label>
                          {uploadElo.isPending && <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>enviando...</span>}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {novoAberto ? (
            <div style={{ marginTop: 10, background: 'var(--light)', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <select className={s.miniInput} value={nf.tipo_documento}
                onChange={(e) => setNf({ ...nf, tipo_documento: e.target.value as TipoDocumentoElo })}>
                {(Object.keys(TIPO_DOC_LABEL) as TipoDocumentoElo[]).map((t) => (
                  <option key={t} value={t}>{TIPO_DOC_LABEL[t]}</option>
                ))}
              </select>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input className={s.miniInput} style={{ flex: 1, minWidth: 120 }} placeholder="De quem (transmitente)"
                  value={nf.de_quem} onChange={(e) => setNf({ ...nf, de_quem: e.target.value })} />
                <input className={s.miniInput} style={{ flex: 1, minWidth: 120 }} placeholder="Para quem (adquirente)"
                  value={nf.para_quem} onChange={(e) => setNf({ ...nf, para_quem: e.target.value })} />
                <DateInput className={s.miniInput} value={nf.data}
                  onChange={(iso) => setNf({ ...nf, data: iso })} />
              </div>
              <textarea className={s.miniInput} rows={2} placeholder="Descrição / observações do elo"
                value={nf.descricao} onChange={(e) => setNf({ ...nf, descricao: e.target.value })} />
              <div className={s.rowBtns}>
                <button className={styles.btnPrimary} disabled={criar.isPending} onClick={() => criar.mutate()}>
                  {criar.isPending ? 'Adicionando...' : '+ Adicionar elo'}
                </button>
                <button className={styles.btnTable} onClick={() => setNovoAberto(false)}>Cancelar</button>
              </div>
            </div>
          ) : (
            <button className={styles.btnTable} style={{ marginTop: 10 }} onClick={() => setNovoAberto(true)}>
              + Adicionar elo à cadeia
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ── Calculadora de Ganho de Capital (imóvel) ──────────────────────────────────
function irpfProgressivo(ganho: number): number {
  // Lei 13.259/2016 — faixas progressivas sobre o ganho
  const faixas: [number, number][] = [
    [5_000_000, 0.15],
    [10_000_000, 0.175],
    [30_000_000, 0.20],
    [Infinity, 0.225],
  ]
  let imposto = 0
  let anterior = 0
  for (const [teto, aliq] of faixas) {
    if (ganho <= anterior) break
    const base = Math.min(ganho, teto) - anterior
    imposto += base * aliq
    anterior = teto
  }
  return imposto
}

function mesesEntre(inicio: Date, fim: Date): number {
  return Math.max(0, (fim.getFullYear() - inicio.getFullYear()) * 12 + (fim.getMonth() - inicio.getMonth()))
}

// Fator de redução do ganho de capital de imóveis (só PF). Retorna a FRAÇÃO do
// ganho que permanece tributável (quanto menor, maior a redução).
// Lei 11.196/2005 (FR1 até nov/2005 e FR2 até a venda) + Lei 7.713/88 (imóveis até 1988).
function fatorReducaoImovel(dataCompra: Date, dataVenda: Date): number {
  const ano = dataCompra.getFullYear()
  let mult7713 = 1
  if (ano <= 1969) mult7713 = 0
  else if (ano <= 1988) mult7713 = (5 * (ano - 1969)) / 100 // fração tributável (7.713/88)
  const nov2005 = new Date(2005, 10, 1)
  const dez2005 = new Date(2005, 11, 1)
  const m1 = dataCompra < nov2005 ? mesesEntre(dataCompra, nov2005) : 0
  const inicioF2 = dataCompra > dez2005 ? dataCompra : dez2005
  const m2 = mesesEntre(inicioF2, dataVenda)
  const fr1 = 1 / Math.pow(1.0035, m1)
  const fr2 = 1 / Math.pow(1.006, m2)
  return mult7713 * fr1 * fr2
}

interface GCResult {
  ganho: number
  fator: number      // fração tributável na PF (1 = sem redução)
  temReducao: boolean
  ganhoPF: number    // ganho já reduzido (base PF)
  impPF: number
  impPJ: number
  impHolding: number
  menorKey: 'pf' | 'pj' | 'holding'
}

function calcularGC(aquisicao: number, venda: number, dataCompra?: string | null, dataVenda?: Date): GCResult {
  const ganho = Math.max(0, venda - aquisicao)
  let fator = 1
  if (dataCompra) {
    const dc = new Date(dataCompra + 'T12:00:00')
    if (!isNaN(dc.getTime())) fator = fatorReducaoImovel(dc, dataVenda ?? new Date())
  }
  const ganhoPF = ganho * fator
  const impPF = irpfProgressivo(ganhoPF)
  const impPJ = ganho * 0.34
  const impHolding = venda * 0.0673
  const menor = Math.min(impPF, impPJ, impHolding)
  const menorKey = menor === impPF ? 'pf' : menor === impHolding ? 'holding' : 'pj'
  return { ganho, fator, temReducao: fator < 0.9999, ganhoPF, impPF, impPJ, impHolding, menorKey }
}

function MoneyInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className={s.moneyWrap}>
      <span className={s.moneyPrefix}>R$</span>
      <input type="number" step="0.01" min="0" className={s.moneyField}
        value={value || ''} onChange={(e) => onChange(parseFloat(e.target.value) || 0)} />
    </div>
  )
}

function CalculadoraGC({ bem }: { bem: Bem }) {
  const [aberto, setAberto] = useState(false)
  const [aquisicao, setAquisicao] = useState<number>(bem.valor_compra ?? bem.valor_ir ?? 0)
  const [venda, setVenda] = useState<number>(bem.valor_mercado ?? 0)
  const [dataVenda, setDataVenda] = useState<string>(new Date().toISOString().slice(0, 10))

  const dvDate = dataVenda ? new Date(dataVenda + 'T12:00:00') : new Date()
  const r = calcularGC(aquisicao, venda, bem.data_compra, isNaN(dvDate.getTime()) ? new Date() : dvDate)
  const reducaoPct = (1 - r.fator) * 100

  const cenarios = [
    {
      key: 'holding', nome: 'PJ Holding Imobiliária', base: 'sobre a venda',
      taxa: '6,73%', imposto: r.impHolding,
      nota: 'Lucro Presumido, imóvel como estoque e atividade imobiliária no objeto social. IRPJ 1,2% + adic. ~0,8% + CSLL 1,08% + PIS 0,65% + COFINS 3%. Sem fator de redução (PJ).',
    },
    {
      key: 'pf', nome: 'Pessoa Física', base: 'sobre o ganho reduzido',
      taxa: '15%–22,5%', imposto: r.impPF,
      nota: r.temReducao
        ? 'Faixas progressivas (Lei 13.259/2016) sobre o ganho já reduzido pelo fator de redução (Leis 11.196/2005 e 7.713/88).'
        : 'Faixas progressivas (Lei 13.259/2016). Cadastre a data da compra para aplicar o fator de redução automaticamente.',
    },
    {
      key: 'pj', nome: 'PJ não imobiliária', base: 'sobre o ganho',
      taxa: '34%', imposto: r.impPJ,
      nota: 'Lucro Real ou Presumido: IRPJ 15% + adicional 10% + CSLL 9% sobre o ganho (venda de imobilizado não usa presunção). No Simples, tributado fora do DAS pelas faixas da PF. Sem fator de redução.',
    },
  ]
  const menor = Math.min(...cenarios.map((c) => c.imposto))

  return (
    <div>
      <button className={s.cadeiaToggle} onClick={() => setAberto(!aberto)}>
        <span>{aberto ? '▾' : '▸'}</span>
        🧮 Calculadora de Ganho de Capital
        <span style={{ color: 'var(--gray-mid)', fontWeight: 600 }}>
          (ganho estimado: {brl(r.ganho)})
        </span>
      </button>

      {aberto && (
        <div className={s.gcBox}>
          <div className={s.gcInputs}>
            <div className={s.field}>
              <span className={s.fieldLabel}>Valor de aquisição</span>
              <MoneyInput value={aquisicao} onChange={setAquisicao} />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Valor estimado de venda</span>
              <MoneyInput value={venda} onChange={setVenda} />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Data da venda (simulação)</span>
              <DateInput className={s.miniInput} value={dataVenda}
                onChange={(iso) => setDataVenda(iso)} />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Ganho de capital</span>
              <span className={s.gcGanho}>{brl(r.ganho)}</span>
            </div>
          </div>

          <div className={s.gcReducao}>
            {bem.data_compra ? (
              r.temReducao ? (
                <>Fator de redução (PF): <b>−{reducaoPct.toFixed(1).replace('.', ',')}%</b> do ganho ·
                  compra em {fmtDate(bem.data_compra)} · ganho tributável na PF: <b>{brl(r.ganhoPF)}</b></>
              ) : (
                <>Sem redução aplicável (imóvel adquirido em {fmtDate(bem.data_compra)}).</>
              )
            ) : (
              <>⚠ Cadastre a <b>data da compra</b> do imóvel para aplicar o fator de redução na PF.</>
            )}
          </div>

          <div className={s.gcCenarios}>
            {cenarios.map((c) => {
              const isMenor = c.imposto === menor && venda > 0
              const efetiva = venda > 0 ? (c.imposto / venda) * 100 : 0
              return (
                <div key={c.key} className={`${s.gcCard} ${isMenor ? s.gcCardBest : ''}`}>
                  <div className={s.gcCardTop}>
                    <span className={s.gcCardNome}>{c.nome}</span>
                    {isMenor && <span className={s.gcBadge}>Menor carga</span>}
                  </div>
                  <div className={s.gcCardTaxa}>{c.taxa} <span>{c.base}</span></div>
                  <div className={s.gcCardImposto}>{brl(c.imposto)}</div>
                  <div className={s.gcCardEfetiva}>
                    {efetiva.toFixed(2).replace('.', ',')}% da venda · líquido {brl(venda - c.imposto)}
                  </div>
                  <div className={s.gcCardNota}>{c.nota}</div>
                </div>
              )
            })}
          </div>
          <p className={s.gcDisclaimer}>
            ⚠️ Estimativa para comparação. Já aplica o fator de redução da PF (Leis 11.196/2005 e 7.713/88),
            mas não considera isenções (imóvel único, reinvestimento em 180 dias), ITBI, adicional de IRPJ
            variável por faturamento nem custos da operação. Confirme sempre no caso concreto.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Tabela consolidada de Ganho de Capital (todos os imóveis) ─────────────────
function TabelaGCImoveis({ bens }: { bens: Bem[] }) {
  const [aberto, setAberto] = useState(false)
  const [excluidos, setExcluidos] = useState<Set<string>>(new Set())
  const imoveis = bens.filter((b) => b.tipo_bem === 'imovel')
  if (imoveis.length === 0) return null

  const toggleBem = (id: string) => setExcluidos((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const hoje = new Date()
  const linhas = imoveis.map((b) => ({
    bem: b,
    incluido: !excluidos.has(b.id),
    r: calcularGC(b.valor_compra ?? b.valor_ir ?? 0, b.valor_mercado ?? 0, b.data_compra, hoje),
  }))
  const tot = linhas.filter((l) => l.incluido).reduce(
    (a, l) => ({
      ganho: a.ganho + l.r.ganho, impPF: a.impPF + l.r.impPF,
      impPJ: a.impPJ + l.r.impPJ, impHolding: a.impHolding + l.r.impHolding,
    }),
    { ganho: 0, impPF: 0, impPJ: 0, impHolding: 0 },
  )
  const nIncluidos = linhas.filter((l) => l.incluido).length
  const cell = (val: number, best: boolean, incluido: boolean) =>
    <td className={`${s.gcTd} ${s.gcTdNum} ${best && incluido ? s.gcTdBest : ''}`}>{brl(val)}</td>

  return (
    <div className={s.card}>
      <div className={s.cardHead} onClick={() => setAberto(!aberto)}>
        <span className={s.bemIcon}>🧮</span>
        <div className={s.grow}>
          <div className={s.bemTitulo}>Ganho de Capital — imóveis ({nIncluidos}/{imoveis.length} nos totais)</div>
          <div className={s.bemMeta}><span>PF (com fator de redução) × PJ 34% × Holding 6,73%, vendendo hoje · marque para incluir/excluir dos totais</span></div>
        </div>
        <span style={{ color: 'var(--gray-mid)', fontSize: 12 }}>{aberto ? '▾' : '▸'}</span>
      </div>
      {aberto && (
        <div className={s.gcTableWrap}>
          <table className={s.gcTable}>
            <thead>
              <tr>
                <th className={s.gcTh} style={{ width: 34 }} title="Incluir nos totais"></th>
                <th className={s.gcTh}>Imóvel</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>Aquisição</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>Venda est.</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>Ganho</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>Redução PF</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>IR PF</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>PJ 34%</th>
                <th className={`${s.gcTh} ${s.gcThNum}`}>Holding 6,73%</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map(({ bem: b, r, incluido }) => (
                <tr key={b.id} className={incluido ? '' : s.gcRowOff}>
                  <td className={s.gcTd} style={{ textAlign: 'center' }}>
                    <input type="checkbox" checked={incluido} onChange={() => toggleBem(b.id)}
                      title={incluido ? 'Excluir dos totais' : 'Incluir nos totais'} />
                  </td>
                  <td className={s.gcTd}>
                    <div className={s.gcNome}>{b.nome}</div>
                    {b.numero_matricula && <div className={s.gcSub}>Mat. {b.numero_matricula}</div>}
                  </td>
                  <td className={`${s.gcTd} ${s.gcTdNum}`}>{brl(b.valor_compra ?? b.valor_ir)}</td>
                  <td className={`${s.gcTd} ${s.gcTdNum}`}>{brl(b.valor_mercado)}</td>
                  <td className={`${s.gcTd} ${s.gcTdNum}`}>{brl(r.ganho)}</td>
                  <td className={`${s.gcTd} ${s.gcTdNum}`}>
                    {r.temReducao ? `−${((1 - r.fator) * 100).toFixed(1).replace('.', ',')}%` : (b.data_compra ? '—' : '⚠ s/ data')}
                  </td>
                  {cell(r.impPF, r.menorKey === 'pf', incluido)}
                  {cell(r.impPJ, r.menorKey === 'pj', incluido)}
                  {cell(r.impHolding, r.menorKey === 'holding', incluido)}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className={`${s.gcTd} ${s.gcTfoot}`} colSpan={4}>Totais ({nIncluidos} imóvel{nIncluidos === 1 ? '' : 'is'})</td>
                <td className={`${s.gcTd} ${s.gcTdNum} ${s.gcTfoot}`}>{brl(tot.ganho)}</td>
                <td className={`${s.gcTd} ${s.gcTfoot}`} />
                <td className={`${s.gcTd} ${s.gcTdNum} ${s.gcTfoot}`}>{brl(tot.impPF)}</td>
                <td className={`${s.gcTd} ${s.gcTdNum} ${s.gcTfoot}`}>{brl(tot.impPJ)}</td>
                <td className={`${s.gcTd} ${s.gcTdNum} ${s.gcTfoot}`}>{brl(tot.impHolding)}</td>
              </tr>
            </tfoot>
          </table>
          <p className={s.gcDisclaimer} style={{ margin: '10px 12px 0' }}>
            ⚠️ Estimativa vendendo hoje, com fator de redução da PF por imóvel. Desmarque um imóvel para tirá-lo dos totais.
            Ajuste valores e data de venda na calculadora de cada imóvel. Não considera isenções nem custos da operação.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Quadro de sócios (bem móvel = cota social) ────────────────────────────────
function SociosSection({ bem }: { bem: Bem }) {
  const qc = useQueryClient()
  const [novoAberto, setNovoAberto] = useState(false)
  const invalidate = () => qc.invalidateQueries({ queryKey: ['patrimonio', bem.cliente_id] })
  const [nf, setNf] = useState<{ nome: string; cpf: string; percentual: string; integralizar: boolean }>(
    { nome: '', cpf: '', percentual: '', integralizar: false }
  )

  const criar = useMutation({
    mutationFn: () => patrimonioApi.criarSocio(bem.id, {
      nome: nf.nome, cpf: nf.cpf || undefined,
      percentual: nf.percentual ? parseFloat(nf.percentual) : undefined,
      integralizar: nf.integralizar, ordem: bem.socios?.length ?? 0,
    }),
    onSuccess: () => { invalidate(); setNovoAberto(false); setNf({ nome: '', cpf: '', percentual: '', integralizar: false }) },
  })
  const toggle = useMutation({
    mutationFn: ({ socioId, integralizar }: { socioId: string; integralizar: boolean }) =>
      patrimonioApi.atualizarSocio(bem.id, socioId, { integralizar }),
    onSuccess: invalidate,
  })
  const deletar = useMutation({
    mutationFn: (socioId: string) => patrimonioApi.deletarSocio(bem.id, socioId),
    onSuccess: invalidate,
  })

  const totalPct = (bem.socios ?? []).reduce((sum, so) => sum + (so.percentual ?? 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className={s.sectionTitle}>👥 Quadro de sócios ({bem.socios?.length ?? 0})</span>
      {(bem.socios?.length ?? 0) > 0 && (
        <div className={s.socioList}>
          {bem.socios.map((so: Socio) => (
            <div key={so.id} className={s.socioRow}>
              <div className={s.grow}>
                <div className={s.socioNome}>{so.nome}</div>
                <div className={s.socioMeta}>
                  {so.cpf || 'sem CPF'}{so.percentual != null && <> · {so.percentual}%</>}
                </div>
              </div>
              <label className={s.socioIntegr} title="Integralizar esta participação na holding">
                <input type="checkbox" checked={so.integralizar}
                  onChange={(e) => toggle.mutate({ socioId: so.id, integralizar: e.target.checked })} />
                Integralizar
              </label>
              <button className={s.anexoDel} title="Remover sócio"
                onClick={() => { if (confirm(`Remover ${so.nome}?`)) deletar.mutate(so.id) }}>×</button>
            </div>
          ))}
          <div className={s.socioTotal}>
            Total: {totalPct.toLocaleString('pt-BR', { maximumFractionDigits: 3 })}%
            {Math.abs(totalPct - 100) > 0.01 && totalPct > 0 && (
              <span className={s.socioAlerta}> ⚠ não soma 100%</span>
            )}
          </div>
        </div>
      )}
      {novoAberto ? (
        <div style={{ background: 'var(--light)', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input className={s.miniInput} style={{ flex: 2, minWidth: 140 }} placeholder="Nome do sócio"
              value={nf.nome} onChange={(e) => setNf({ ...nf, nome: e.target.value })} />
            <input className={s.miniInput} style={{ flex: 1, minWidth: 120 }} placeholder="CPF"
              value={nf.cpf} onChange={(e) => setNf({ ...nf, cpf: e.target.value })} />
            <input type="number" step="0.001" min="0" max="100" className={s.miniInput} style={{ width: 90 }} placeholder="%"
              value={nf.percentual} onChange={(e) => setNf({ ...nf, percentual: e.target.value })} />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, cursor: 'pointer' }}>
            <input type="checkbox" checked={nf.integralizar}
              onChange={(e) => setNf({ ...nf, integralizar: e.target.checked })} />
            Integralizar esta participação na holding
          </label>
          <div className={s.rowBtns}>
            <button className={styles.btnPrimary} disabled={!nf.nome || criar.isPending} onClick={() => criar.mutate()}>
              {criar.isPending ? 'Adicionando...' : '+ Adicionar sócio'}
            </button>
            <button className={styles.btnTable} onClick={() => setNovoAberto(false)}>Cancelar</button>
          </div>
        </div>
      ) : (
        <button className={styles.btnTable} style={{ alignSelf: 'flex-start' }} onClick={() => setNovoAberto(true)}>
          + Adicionar sócio
        </button>
      )}
    </div>
  )
}

// ── Card de bem ───────────────────────────────────────────────────────────────
function BemCard({ bem }: { bem: Bem }) {
  const qc = useQueryClient()
  const [aberto, setAberto] = useState(false)
  const [editando, setEditando] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const invalidate = () => qc.invalidateQueries({ queryKey: ['patrimonio', bem.cliente_id] })

  const atualizar = useMutation({
    mutationFn: (data: Partial<Bem>) => patrimonioApi.atualizar(bem.id, data),
    onSuccess: () => { invalidate(); setEditando(false) },
  })
  const deletar = useMutation({
    mutationFn: () => patrimonioApi.deletar(bem.id),
    onSuccess: invalidate,
  })
  const uploadAnexo = useMutation({
    mutationFn: (file: File) => patrimonioApi.uploadAnexo(bem.id, file),
    onSuccess: invalidate,
  })
  const delAnexo = useMutation({
    mutationFn: (anexoId: string) => patrimonioApi.deletarAnexo(bem.id, anexoId),
    onSuccess: invalidate,
  })

  const real = norm(bem.proprietario_real)
  const mat = norm(bem.proprietario_matricula)
  const propMatch = real && mat ? (real === mat ? 'ok' : 'diff') : null

  if (editando) {
    return (
      <div className={s.card}>
        <div style={{ padding: 14 }}>
          <BemForm
            initial={{
              tipo_bem: bem.tipo_bem, nome: bem.nome, descricao: bem.descricao ?? '',
              valor_compra: bem.valor_compra ?? undefined, valor_mercado: bem.valor_mercado ?? undefined,
              valor_ir: bem.valor_ir ?? undefined, data_compra: bem.data_compra ?? '',
              objetivo: bem.objetivo ?? undefined, descricao_matricula: bem.descricao_matricula ?? '',
              numero_matricula: bem.numero_matricula ?? '', cartorio: bem.cartorio ?? '',
              status: bem.status, integralizar_holding: bem.integralizar_holding,
              proprietario_real: bem.proprietario_real ?? '', proprietario_matricula: bem.proprietario_matricula ?? '',
              tem_gravame: bem.tem_gravame, gravame_descricao: bem.gravame_descricao ?? '',
              observacoes: bem.observacoes ?? '',
              empresa_nome: bem.empresa_nome ?? '', empresa_cnpj: bem.empresa_cnpj ?? '',
              capital_social: bem.capital_social ?? undefined, valor_balanco: bem.valor_balanco ?? undefined,
              data_balanco: bem.data_balanco ?? '',
            }}
            saving={atualizar.isPending}
            onCancel={() => setEditando(false)}
            onSave={(data) => atualizar.mutate({ ...data, data_compra: data.data_compra || null, data_balanco: data.data_balanco || null } as Partial<Bem>)}
          />
        </div>
      </div>
    )
  }

  return (
    <div className={s.card}>
      <div className={s.cardHead} onClick={() => setAberto(!aberto)}>
        <span className={s.bemIcon}>{bem.tipo_bem === 'imovel' ? '🏠' : '📦'}</span>
        <div className={s.grow}>
          <div className={s.bemTitulo}>
            {bem.nome}
            {bem.numero_matricula && <span className={s.matriculaTag}>Matrícula {bem.numero_matricula}</span>}
            {bem.integralizar_holding && <span className={`${s.tag} ${s.tagHolding}`}>Holding</span>}
            {bem.tem_gravame && <span className={`${s.tag} ${s.tagGravame}`}>Gravame</span>}
          </div>
          <div className={s.bemMeta}>
            {bem.objetivo && <span>🎯 {OBJETIVO_LABEL[bem.objetivo]}</span>}
            <span>💰 Mercado: {brl(bem.valor_mercado)}</span>
            {bem.tipo_bem === 'movel' && bem.empresa_nome && <span>🏢 {bem.empresa_nome}</span>}
          </div>
        </div>
        <span className={`${s.badgeStatus} ${s[`st_${bem.status}`]}`}>{STATUS_LABEL[bem.status]}</span>
        <span style={{ color: 'var(--gray-mid)', fontSize: 12 }}>{aberto ? '▾' : '▸'}</span>
      </div>

      {aberto && (
        <div className={s.body}>
          {bem.descricao && <div className={s.fieldValue}>{bem.descricao}</div>}

          <div className={s.grid}>
            <div className={s.field}><span className={s.fieldLabel}>Valor de compra</span><span className={s.fieldValue}>{brl(bem.valor_compra)}</span></div>
            <div className={s.field}><span className={s.fieldLabel}>Valor de mercado</span><span className={s.fieldValue}>{brl(bem.valor_mercado)}</span></div>
            <div className={s.field}><span className={s.fieldLabel}>Valor no IR</span><span className={s.fieldValue}>{brl(bem.valor_ir)}</span></div>
            <div className={s.field}><span className={s.fieldLabel}>Data da compra</span><span className={s.fieldValue}>{fmtDate(bem.data_compra)}</span></div>
            {bem.tipo_bem === 'imovel' && (
              <>
                <div className={s.field}><span className={s.fieldLabel}>Nº matrícula</span><span className={s.fieldValue}>{bem.numero_matricula || '—'}</span></div>
                <div className={s.field}><span className={s.fieldLabel}>Cartório</span><span className={s.fieldValue}>{bem.cartorio || '—'}</span></div>
              </>
            )}
          </div>

          {bem.descricao_matricula && (
            <div className={s.field}>
              <span className={s.fieldLabel}>Descrição conforme matrícula</span>
              <span className={s.fieldValue}>{bem.descricao_matricula}</span>
            </div>
          )}

          {/* Proprietários */}
          <div className={s.propBox}>
            <div className={s.propCard}>
              <div className={s.fieldLabel}>Proprietário real</div>
              <div className={s.fieldValue}>{bem.proprietario_real || '—'}</div>
            </div>
            <div className={s.propCard}>
              <div className={s.fieldLabel}>Proprietário na matrícula</div>
              <div className={s.fieldValue}>{bem.proprietario_matricula || '—'}</div>
            </div>
            {propMatch === 'ok' && (
              <div className={`${s.propMatch} ${s.matchOk}`}>✓ Proprietário confere</div>
            )}
            {propMatch === 'diff' && (
              <div className={`${s.propMatch} ${s.matchDiff}`}>⚠ Diverge da matrícula</div>
            )}
          </div>

          {bem.tem_gravame && (
            <div className={s.field}>
              <span className={s.fieldLabel}>Gravame / ônus</span>
              <span className={s.fieldValue}>{bem.gravame_descricao || 'Sim (sem detalhes)'}</span>
            </div>
          )}

          {bem.observacoes && (
            <div className={s.field}>
              <span className={s.fieldLabel}>Observações gerais</span>
              <span className={s.fieldValue}>{bem.observacoes}</span>
            </div>
          )}

          {/* Anexos */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span className={s.sectionTitle}>📎 Documentos anexados</span>
            {bem.anexos.length > 0 && (
              <div className={s.anexoList}>
                {bem.anexos.map((a) => (
                  <div key={a.id} className={s.anexoItem}>
                    <span className={s.anexoNome}>{a.filename}</span>
                    {a.drive_link
                      ? <a className={s.anexoLink} href={a.drive_link} target="_blank" rel="noreferrer">Abrir no Drive ↗</a>
                      : <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>salvo local</span>}
                    <button className={s.anexoDel} title="Remover"
                      onClick={() => { if (confirm('Remover anexo?')) delAnexo.mutate(a.id) }}>×</button>
                  </div>
                ))}
              </div>
            )}
            <label className={s.uploadBtn}>
              {uploadAnexo.isPending ? '⏳ Enviando...' : '＋ Anexar arquivo'}
              <input ref={fileRef} type="file" style={{ display: 'none' }} disabled={uploadAnexo.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) uploadAnexo.mutate(file)
                  if (fileRef.current) fileRef.current.value = ''
                }} />
            </label>
          </div>

          {/* Calculadora de Ganho de Capital (só imóvel) */}
          {bem.tipo_bem === 'imovel' && <CalculadoraGC bem={bem} />}

          {/* Cadeia sucessória (só imóvel) */}
          {bem.tipo_bem === 'imovel' && <CadeiaSection bem={bem} />}

          {/* Cota social / participação societária (só móvel) */}
          {bem.tipo_bem === 'movel' && (bem.empresa_nome || bem.empresa_cnpj || bem.capital_social != null || bem.valor_balanco != null) && (
            <div className={s.grid}>
              {bem.empresa_nome && <div className={s.field}><span className={s.fieldLabel}>Empresa</span><span className={s.fieldValue}>{bem.empresa_nome}</span></div>}
              {bem.empresa_cnpj && <div className={s.field}><span className={s.fieldLabel}>CNPJ</span><span className={s.fieldValue}>{bem.empresa_cnpj}</span></div>}
              {bem.capital_social != null && <div className={s.field}><span className={s.fieldLabel}>Capital social</span><span className={s.fieldValue}>{brl(bem.capital_social)}</span></div>}
              {bem.valor_balanco != null && <div className={s.field}><span className={s.fieldLabel}>Valor do balanço (PL)</span><span className={s.fieldValue}>{brl(bem.valor_balanco)}</span></div>}
              {bem.data_balanco && <div className={s.field}><span className={s.fieldLabel}>Data do balanço</span><span className={s.fieldValue}>{fmtDate(bem.data_balanco)}</span></div>}
            </div>
          )}
          {bem.tipo_bem === 'movel' && <SociosSection bem={bem} />}

          {/* Ações do bem */}
          <div className={s.rowBtns} style={{ marginTop: 4, borderTop: '1px solid var(--gray-border)', paddingTop: 12 }}>
            <button className={styles.btnTable} onClick={() => setEditando(true)}>Editar</button>
            <button className={styles.btnDanger}
              onClick={() => { if (confirm(`Remover o bem "${bem.nome}"?`)) deletar.mutate() }}>
              Remover
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Seção principal ───────────────────────────────────────────────────────────
export default function PatrimonioSection({ clienteId }: { clienteId: string }) {
  const qc = useQueryClient()
  const [novoAberto, setNovoAberto] = useState(false)

  const { data: bens = [], isLoading } = useQuery({
    queryKey: ['patrimonio', clienteId],
    queryFn: () => patrimonioApi.listar(clienteId),
  })

  const criar = useMutation({
    mutationFn: (data: FormState) =>
      patrimonioApi.criar({
        ...data,
        cliente_id: clienteId,
        data_compra: data.data_compra || undefined,
        data_balanco: data.data_balanco || undefined,
      } as BemCreate),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patrimonio', clienteId] })
      setNovoAberto(false)
    },
    onError: () => alert('Não foi possível salvar o bem. Verifique os campos e tente novamente.'),
  })

  const totalMercado = bens.reduce((sum, b) => sum + (b.valor_mercado ?? 0), 0)
  const totalHolding = bens.filter((b) => b.integralizar_holding).length

  const [exportando, setExportando] = useState<'xls' | 'pdf' | null>(null)
  const exportar = async (fmt: 'xls' | 'pdf') => {
    setExportando(fmt)
    try {
      const blob = fmt === 'xls'
        ? await patrimonioApi.exportXls(clienteId)
        : await patrimonioApi.exportPdf(clienteId)
      baixarBlob(blob, `Patrimonio.${fmt === 'xls' ? 'xlsx' : 'pdf'}`)
    } catch {
      alert('Não foi possível gerar o arquivo. Tente novamente.')
    } finally {
      setExportando(null)
    }
  }

  return (
    <div className={s.wrap}>
      {bens.length > 0 && (
        <div className={s.resumo}>
          <div className={s.resumoCard}>
            <div className={s.resumoLabel}>Bens</div>
            <div className={s.resumoValor}>{bens.length}</div>
          </div>
          <div className={s.resumoCard}>
            <div className={s.resumoLabel}>Valor de mercado</div>
            <div className={`${s.resumoValor} ${s.teal}`}>{brl(totalMercado)}</div>
          </div>
          <div className={s.resumoCard}>
            <div className={s.resumoLabel}>Para a holding</div>
            <div className={s.resumoValor}>{totalHolding}</div>
          </div>
        </div>
      )}

      {bens.length > 0 && <TabelaGCImoveis bens={bens} />}

      <div className={s.header}>
        <span className={s.headerTitle}>Patrimônio</span>
        <button className={styles.btnPrimary} onClick={() => setNovoAberto(!novoAberto)}>
          {novoAberto ? 'Cancelar' : '+ Novo bem'}
        </button>
      </div>

      {novoAberto && (
        <div className={s.card}>
          <div style={{ padding: 14 }}>
            <BemForm
              initial={emptyForm()}
              saving={criar.isPending}
              onCancel={() => setNovoAberto(false)}
              onSave={(data) => criar.mutate(data)}
            />
          </div>
        </div>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : bens.length === 0 && !novoAberto ? (
        <p className={styles.empty}>Nenhum bem cadastrado. Clique em "+ Novo bem" para começar o inventário patrimonial.</p>
      ) : (
        <div className={s.list}>
          {bens.map((b) => <BemCard key={b.id} bem={b} />)}
        </div>
      )}

      {bens.length > 0 && (
        <div className={s.exportBar}>
          <span className={s.exportLabel}>Exportar inventário</span>
          <button className={s.exportBtn} disabled={exportando !== null} onClick={() => exportar('xls')}>
            {exportando === 'xls' ? '⏳ Gerando...' : '⬇ Excel (XLS)'}
          </button>
          <button className={`${s.exportBtn} ${s.exportPdf}`} disabled={exportando !== null} onClick={() => exportar('pdf')}>
            {exportando === 'pdf' ? '⏳ Gerando...' : '📄 PDF'}
          </button>
        </div>
      )}
    </div>
  )
}
