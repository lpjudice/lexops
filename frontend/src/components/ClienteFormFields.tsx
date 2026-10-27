import type { ClienteCreate } from '../api/clientes'
import {
  applyDocMask, brParaIso, buscarCep, ESTADO_CIVIL_OPCOES,
  maskCEP, maskCPF, maskDataBr, maskTelefone,
} from '../utils/masks'
import styles from '../pages/Page.module.css'

/** Converte a data de nascimento (DD/MM/AAAA no form) para ISO antes de enviar. */
export function comDataIso<T extends { data_nascimento?: string | null }>(obj: T): T {
  return { ...obj, data_nascimento: brParaIso(obj.data_nascimento) || null }
}

export function EnderecoFields({ form, onChange }: { form: ClienteCreate; onChange: (f: ClienteCreate) => void }) {
  async function onCepBlur() {
    const res = await buscarCep(form.cep ?? '')
    if (!res) return
    onChange({
      ...form,
      logradouro: res.logradouro || form.logradouro,
      bairro: res.bairro || form.bairro,
      cidade: res.localidade || form.cidade,
      uf: res.uf || form.uf,
    })
  }
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>CEP</label>
        <input className={styles.input} placeholder="00000-000" value={form.cep ?? ''}
          onChange={(e) => onChange({ ...form, cep: maskCEP(e.target.value) })}
          onBlur={onCepBlur} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Logradouro</label>
        <input className={styles.input} value={form.logradouro ?? ''}
          onChange={(e) => onChange({ ...form, logradouro: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Número</label>
        <input className={styles.input} value={form.numero ?? ''}
          onChange={(e) => onChange({ ...form, numero: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Complemento</label>
        <input className={styles.input} value={form.complemento ?? ''}
          onChange={(e) => onChange({ ...form, complemento: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Bairro</label>
        <input className={styles.input} value={form.bairro ?? ''}
          onChange={(e) => onChange({ ...form, bairro: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Cidade</label>
        <input className={styles.input} value={form.cidade ?? ''}
          onChange={(e) => onChange({ ...form, cidade: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>UF</label>
        <input className={styles.input} maxLength={2} style={{ maxWidth: 80 }} value={form.uf ?? ''}
          onChange={(e) => onChange({ ...form, uf: e.target.value.toUpperCase().slice(0, 2) })} />
      </div>
    </>
  )
}

export default function ClienteFormFields({ form, onChange }: { form: ClienteCreate; onChange: (f: ClienteCreate) => void }) {
  const isPF = form.tipo === 'PF'
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Tipo *</label>
        <select className={styles.input} value={form.tipo}
          onChange={(e) => onChange({ ...form, tipo: e.target.value as 'PF' | 'PJ', cpf_cnpj: '' })}>
          <option value="PF">Pessoa Física</option>
          <option value="PJ">Pessoa Jurídica</option>
        </select>
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Nome completo *' : 'Razão social *'}</label>
        <input className={styles.input} value={form.nome ?? ''}
          onChange={(e) => onChange({ ...form, nome: e.target.value })} required />
      </div>
      {!isPF && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Nome fantasia</label>
          <input className={styles.input} value={form.nome_fantasia ?? ''}
            onChange={(e) => onChange({ ...form, nome_fantasia: e.target.value })} />
        </div>
      )}
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'CPF' : 'CNPJ'}</label>
        <input className={styles.input}
          placeholder={isPF ? '000.000.000-00' : '00.000.000/0000-00'}
          value={form.cpf_cnpj ?? ''}
          onChange={(e) => onChange({ ...form, cpf_cnpj: applyDocMask(e.target.value, form.tipo) })} />
      </div>

      {isPF && (
        <>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>RG</label>
            <input className={styles.input} value={form.rg ?? ''}
              onChange={(e) => onChange({ ...form, rg: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data de nascimento</label>
            <input className={styles.input} inputMode="numeric" placeholder="DD/MM/AAAA" maxLength={10}
              value={form.data_nascimento ?? ''}
              onChange={(e) => onChange({ ...form, data_nascimento: maskDataBr(e.target.value) })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nacionalidade</label>
            <input className={styles.input} placeholder="ex.: brasileiro(a)" value={form.nacionalidade ?? ''}
              onChange={(e) => onChange({ ...form, nacionalidade: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Estado civil</label>
            <select className={styles.input} value={form.estado_civil ?? ''}
              onChange={(e) => onChange({ ...form, estado_civil: e.target.value })}>
              <option value="">—</option>
              {ESTADO_CIVIL_OPCOES.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Profissão</label>
            <input className={styles.input} value={form.profissao ?? ''}
              onChange={(e) => onChange({ ...form, profissao: e.target.value })} />
          </div>
        </>
      )}

      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Email' : 'Email comercial'}</label>
        <input type="email" className={styles.input} value={form.email ?? ''}
          onChange={(e) => onChange({ ...form, email: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Telefone (WhatsApp)' : 'Telefone comercial'}</label>
        <input className={styles.input} placeholder="(00) 0.0000-0000"
          value={form.telefone ?? ''}
          onChange={(e) => onChange({ ...form, telefone: maskTelefone(e.target.value) })} />
      </div>
      {!isPF && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>WhatsApp comercial</label>
          <input className={styles.input} placeholder="(00) 0.0000-0000"
            value={form.whatsapp ?? ''}
            onChange={(e) => onChange({ ...form, whatsapp: maskTelefone(e.target.value) })} />
        </div>
      )}

      <EnderecoFields form={form} onChange={onChange} />

      {!isPF && (
        <>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável</label>
            <input className={styles.input} value={form.responsavel_nome ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_nome: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>CPF do responsável</label>
            <input className={styles.input} placeholder="000.000.000-00"
              value={form.responsavel_cpf ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_cpf: maskCPF(e.target.value) })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Email do responsável</label>
            <input type="email" className={styles.input} value={form.responsavel_email ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_email: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Telefone do responsável (WhatsApp)</label>
            <input className={styles.input} placeholder="(00) 0.0000-0000"
              value={form.responsavel_telefone ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_telefone: maskTelefone(e.target.value) })} />
          </div>
        </>
      )}

      <div className={styles.formRow}>
        <label className={styles.formLabel}>Observações</label>
        <textarea className={styles.input} rows={2} value={form.observacoes ?? ''}
          onChange={(e) => onChange({ ...form, observacoes: e.target.value })} />
      </div>
    </>
  )
}
