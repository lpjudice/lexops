/**
 * Campo de "Escopo e recomendações" do contrato — textarea + templates salvos
 * (texto pré-formatado reaproveitável). Escolher um template CARREGA o texto no
 * campo (substitui o que estiver); dá pra editar depois e salvar como novo.
 * Mesmo padrão dos templates de poderes da procuração.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { contratosApi } from '../api/contratos'

interface Props {
  value: string
  onChange: (texto: string) => void
  rows?: number
}

const caixa: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '8px 12px', fontSize: 14, borderRadius: 8,
  border: '1px solid #e5e7eb', fontFamily: 'inherit', color: '#1d1e20', background: '#fff',
}
const botao: React.CSSProperties = {
  padding: '5px 10px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb',
  background: '#fff', cursor: 'pointer', color: '#374151',
}

export default function EscopoEditor({ value, onChange, rows = 5 }: Props) {
  const qc = useQueryClient()
  const [templateId, setTemplateId] = useState('')

  const { data: templates = [] } = useQuery({
    queryKey: ['escopo-templates'],
    queryFn: () => contratosApi.listarEscopoTemplates(),
    staleTime: 30_000,
  })

  const criar = useMutation({
    mutationFn: contratosApi.criarEscopoTemplate,
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ['escopo-templates'] })
      setTemplateId(novo.id)
    },
    onError: (e: any) => alert(`Erro ao salvar template:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const excluir = useMutation({
    mutationFn: contratosApi.excluirEscopoTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['escopo-templates'] })
      setTemplateId('')
    },
  })

  const carregar = (id: string) => {
    setTemplateId(id)
    const t = templates.find((x) => x.id === id)
    if (!t) return
    if (value.trim() && value.trim() !== t.texto.trim() && !confirm('Substituir o texto atual pelo do template?')) {
      setTemplateId('')
      return
    }
    onChange(t.texto)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <select style={{ ...caixa, flex: 1 }} value={templateId} onChange={(e) => carregar(e.target.value)}>
          <option value="">— Carregar um template salvo —</option>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
        </select>
        {templateId && (
          <button type="button" style={{ ...botao, color: '#b91c1c' }} title="Excluir este template salvo"
            onClick={() => { if (confirm('Excluir este template salvo? Não afeta contratos já cadastrados.')) excluir.mutate(templateId) }}>
            🗑️
          </button>
        )}
      </div>
      <textarea style={caixa} rows={rows} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder="Escopo do contrato e recomendações pra equipe (ex.: o que foi contratado, prazos combinados, cuidados com o cliente...)" />
      <div>
        <button type="button" style={botao} disabled={!value.trim() || criar.isPending}
          onClick={() => {
            const nome = prompt('Nome para identificar esse template depois:')
            if (nome?.trim()) criar.mutate({ nome: nome.trim(), texto: value })
          }}>
          💾 Salvar como template
        </button>
      </div>
    </div>
  )
}
