import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import {
  applyDocMask, buscarCep, ESTADO_CIVIL_OPCOES, maskCEP, maskCPF, maskTelefone,
} from '../utils/masks'
import cs from './CadastroPublicoPage.module.css'

type Tipo = 'PF' | 'PJ'

interface FormState {
  tipo: Tipo
  nome: string
  nome_fantasia: string
  cpf_cnpj: string
  rg: string
  data_nascimento: string
  estado_civil: string
  profissao: string
  email: string
  telefone: string
  whatsapp: string
  cep: string
  logradouro: string
  numero: string
  complemento: string
  bairro: string
  cidade: string
  uf: string
  empresas_vinculadas: string
  responsavel_nome: string
  responsavel_cpf: string
  responsavel_email: string
  responsavel_telefone: string
  observacoes: string
}

const EMPTY: FormState = {
  tipo: 'PF', nome: '', nome_fantasia: '', cpf_cnpj: '', rg: '', data_nascimento: '',
  estado_civil: '', profissao: '', email: '', telefone: '', whatsapp: '', cep: '',
  logradouro: '', numero: '', complemento: '', bairro: '', cidade: '', uf: '',
  empresas_vinculadas: '', responsavel_nome: '', responsavel_cpf: '',
  responsavel_email: '', responsavel_telefone: '', observacoes: '',
}

interface FormContexto {
  ok: boolean
  is_update: boolean
  rotulo: string | null
  consentimento_texto: string
  tipo_sugerido: Tipo | null
  prefill: Partial<Record<keyof FormState, string>>
}

export default function CadastroPublicoPage() {
  const { token } = useParams<{ token: string }>()
  const [estado, setEstado] = useState<'carregando' | 'invalido' | 'form' | 'enviando' | 'enviado'>('carregando')
  const [erroLink, setErroLink] = useState<string>('')
  const [ctx, setCtx] = useState<FormContexto | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [files, setFiles] = useState<File[]>([])
  const [consentimento, setConsentimento] = useState(false)
  const [erroEnvio, setErroEnvio] = useState<string>('')
  const [ehUpdate, setEhUpdate] = useState(false)

  // Sem token => link genérico de captação (/cadastro); com token => convite.
  const apiBase = token ? `/api/publico/cadastro/${token}` : '/api/publico/cadastro'

  useEffect(() => {
    let ativo = true
    fetch(apiBase)
      .then(async (r) => {
        if (!r.ok) {
          const msg = r.status === 410 ? 'Este link expirou.' : 'Link inválido ou revogado.'
          throw new Error(msg)
        }
        return r.json() as Promise<FormContexto>
      })
      .then((data) => {
        if (!ativo) return
        setCtx(data)
        setForm((f) => ({
          ...f,
          ...(data.prefill as Partial<FormState>),
          tipo: data.tipo_sugerido ?? f.tipo,
        }))
        setEstado('form')
      })
      .catch((e) => {
        if (!ativo) return
        setErroLink(e.message || 'Link inválido.')
        setEstado('invalido')
      })
    return () => { ativo = false }
  }, [apiBase])

  const isPF = form.tipo === 'PF'
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }))

  async function onCepBlur() {
    const res = await buscarCep(form.cep)
    if (!res) return
    set({
      logradouro: res.logradouro || form.logradouro,
      bairro: res.bairro || form.bairro,
      cidade: res.localidade || form.cidade,
      uf: res.uf || form.uf,
    })
  }

  const anexoLabel = useMemo(
    () => (isPF ? 'Documento de identidade (RG/CNH)' : 'Contrato social'),
    [isPF],
  )

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErroEnvio('')
    if (!form.nome.trim()) { setErroEnvio('Informe o nome.'); return }
    if (!consentimento) { setErroEnvio('É necessário aceitar o termo de consentimento.'); return }

    setEstado('enviando')
    const payload = { ...form, consentimento: true }
    const fd = new FormData()
    fd.append('payload', JSON.stringify(payload))
    files.forEach((f) => fd.append('files', f))
    try {
      const r = await fetch(apiBase, { method: 'POST', body: fd })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body?.detail || 'Não foi possível enviar. Tente novamente.')
      }
      const data = await r.json()
      setEhUpdate(!!data.is_update)
      setEstado('enviado')
    } catch (err: any) {
      setErroEnvio(err.message || 'Erro ao enviar.')
      setEstado('form')
    }
  }

  if (estado === 'carregando') {
    return <div className={cs.wrap}><div className={cs.card}><p className={cs.muted}>Carregando…</p></div></div>
  }

  if (estado === 'invalido') {
    return (
      <div className={cs.wrap}>
        <div className={cs.card}>
          <h1 className={cs.titulo}>Link indisponível</h1>
          <p className={cs.muted}>{erroLink}</p>
          <p className={cs.muted}>Se você recebeu este link do escritório, peça um novo.</p>
        </div>
      </div>
    )
  }

  if (estado === 'enviado') {
    return (
      <div className={cs.wrap}>
        <div className={cs.card}>
          <div className={cs.check}>✓</div>
          <h1 className={cs.titulo}>Dados enviados!</h1>
          <p className={cs.muted}>
            {ehUpdate
              ? 'Recebemos a atualização dos seus dados. Nossa equipe vai conferir e confirmar.'
              : 'Recebemos seu cadastro. Nossa equipe vai conferir e dar continuidade.'}
          </p>
          <p className={cs.muted}>Obrigado! Você já pode fechar esta página.</p>
        </div>
      </div>
    )
  }

  const enviando = estado === 'enviando'

  return (
    <div className={cs.wrap}>
      <form className={cs.card} onSubmit={enviar}>
        <h1 className={cs.titulo}>Cadastro</h1>
        <p className={cs.muted}>
          {ctx?.is_update
            ? 'Confira e atualize seus dados abaixo.'
            : 'Preencha seus dados para darmos início ao atendimento.'}
          {' '}Nenhum campo é obrigatório além do nome.
        </p>

        <div className={cs.tipoToggle}>
          <button type="button" className={isPF ? cs.tipoAtivo : cs.tipoBtn}
            onClick={() => set({ tipo: 'PF', cpf_cnpj: '' })}>Pessoa Física</button>
          <button type="button" className={!isPF ? cs.tipoAtivo : cs.tipoBtn}
            onClick={() => set({ tipo: 'PJ', cpf_cnpj: '' })}>Pessoa Jurídica</button>
        </div>

        <label className={cs.label}>{isPF ? 'Nome completo' : 'Razão social'}
          <input className={cs.input} value={form.nome} onChange={(e) => set({ nome: e.target.value })} />
        </label>

        {!isPF && (
          <label className={cs.label}>Nome fantasia
            <input className={cs.input} value={form.nome_fantasia} onChange={(e) => set({ nome_fantasia: e.target.value })} />
          </label>
        )}

        <label className={cs.label}>{isPF ? 'CPF' : 'CNPJ'}
          <input className={cs.input} inputMode="numeric"
            placeholder={isPF ? '000.000.000-00' : '00.000.000/0000-00'}
            value={form.cpf_cnpj} onChange={(e) => set({ cpf_cnpj: applyDocMask(e.target.value, form.tipo) })} />
        </label>

        {isPF && (
          <>
            <div className={cs.row2}>
              <label className={cs.label}>RG
                <input className={cs.input} value={form.rg} onChange={(e) => set({ rg: e.target.value })} />
              </label>
              <label className={cs.label}>Data de nascimento
                <input type="date" className={cs.input} value={form.data_nascimento}
                  onChange={(e) => set({ data_nascimento: e.target.value })} />
              </label>
            </div>
            <div className={cs.row2}>
              <label className={cs.label}>Estado civil
                <select className={cs.input} value={form.estado_civil} onChange={(e) => set({ estado_civil: e.target.value })}>
                  <option value="">—</option>
                  {ESTADO_CIVIL_OPCOES.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </label>
              <label className={cs.label}>Profissão
                <input className={cs.input} value={form.profissao} onChange={(e) => set({ profissao: e.target.value })} />
              </label>
            </div>
          </>
        )}

        <div className={cs.row2}>
          <label className={cs.label}>{isPF ? 'E-mail' : 'E-mail comercial'}
            <input type="email" className={cs.input} value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </label>
          <label className={cs.label}>{isPF ? 'Telefone (WhatsApp)' : 'Telefone comercial'}
            <input className={cs.input} inputMode="tel" placeholder="(00) 0.0000-0000"
              value={form.telefone} onChange={(e) => set({ telefone: maskTelefone(e.target.value) })} />
          </label>
        </div>
        {!isPF && (
          <label className={cs.label}>WhatsApp comercial
            <input className={cs.input} inputMode="tel" placeholder="(00) 0.0000-0000"
              value={form.whatsapp} onChange={(e) => set({ whatsapp: maskTelefone(e.target.value) })} />
          </label>
        )}

        <fieldset className={cs.fieldset}>
          <legend className={cs.legend}>{isPF ? 'Endereço' : 'Endereço comercial'}</legend>
          <div className={cs.row2}>
            <label className={cs.label}>CEP
              <input className={cs.input} inputMode="numeric" placeholder="00000-000"
                value={form.cep} onChange={(e) => set({ cep: maskCEP(e.target.value) })} onBlur={onCepBlur} />
            </label>
            <label className={cs.label}>Número
              <input className={cs.input} value={form.numero} onChange={(e) => set({ numero: e.target.value })} />
            </label>
          </div>
          <label className={cs.label}>Logradouro
            <input className={cs.input} value={form.logradouro} onChange={(e) => set({ logradouro: e.target.value })} />
          </label>
          <div className={cs.row2}>
            <label className={cs.label}>Complemento
              <input className={cs.input} value={form.complemento} onChange={(e) => set({ complemento: e.target.value })} />
            </label>
            <label className={cs.label}>Bairro
              <input className={cs.input} value={form.bairro} onChange={(e) => set({ bairro: e.target.value })} />
            </label>
          </div>
          <div className={cs.row2}>
            <label className={cs.label}>Cidade
              <input className={cs.input} value={form.cidade} onChange={(e) => set({ cidade: e.target.value })} />
            </label>
            <label className={cs.label}>UF
              <input className={cs.input} maxLength={2} value={form.uf}
                onChange={(e) => set({ uf: e.target.value.toUpperCase().slice(0, 2) })} />
            </label>
          </div>
        </fieldset>

        {isPF ? (
          <label className={cs.label}>Empresas vinculadas ao seu CPF
            <span className={cs.hint}>Opcional — uma por linha, se houver.</span>
            <textarea className={cs.input} rows={2} value={form.empresas_vinculadas}
              onChange={(e) => set({ empresas_vinculadas: e.target.value })} />
          </label>
        ) : (
          <fieldset className={cs.fieldset}>
            <legend className={cs.legend}>Responsável</legend>
            <label className={cs.label}>Nome
              <input className={cs.input} value={form.responsavel_nome} onChange={(e) => set({ responsavel_nome: e.target.value })} />
            </label>
            <div className={cs.row2}>
              <label className={cs.label}>CPF
                <input className={cs.input} inputMode="numeric" placeholder="000.000.000-00"
                  value={form.responsavel_cpf} onChange={(e) => set({ responsavel_cpf: maskCPF(e.target.value) })} />
              </label>
              <label className={cs.label}>Telefone (WhatsApp)
                <input className={cs.input} inputMode="tel" placeholder="(00) 0.0000-0000"
                  value={form.responsavel_telefone} onChange={(e) => set({ responsavel_telefone: maskTelefone(e.target.value) })} />
              </label>
            </div>
            <label className={cs.label}>E-mail
              <input type="email" className={cs.input} value={form.responsavel_email} onChange={(e) => set({ responsavel_email: e.target.value })} />
            </label>
          </fieldset>
        )}

        <label className={cs.label}>Observações
          <textarea className={cs.input} rows={2} value={form.observacoes} onChange={(e) => set({ observacoes: e.target.value })} />
        </label>

        <div className={cs.upload}>
          <label className={cs.label}>{anexoLabel}
            <span className={cs.hint}>Não é obrigatório agora — você pode enviar depois.</span>
            <input type="file" multiple className={cs.file}
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
          </label>
          {files.length > 0 && (
            <p className={cs.muted}>{files.length} arquivo(s) selecionado(s).</p>
          )}
        </div>

        <label className={cs.consent}>
          <input type="checkbox" checked={consentimento} onChange={(e) => setConsentimento(e.target.checked)} />
          <span>{ctx?.consentimento_texto}</span>
        </label>

        {erroEnvio && <p className={cs.erro}>⚠ {erroEnvio}</p>}

        <button type="submit" className={cs.enviar} disabled={enviando}>
          {enviando ? 'Enviando…' : 'Enviar cadastro'}
        </button>
      </form>
    </div>
  )
}
