import { useQuery } from '@tanstack/react-query'
import { type NotaFiscalOut } from '../api/fiscal'

const fmtBRL = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

interface Pagante {
  cpf_cnpj: string
  nome: string
  email?: string
  nfs: NotaFiscalOut[]
  valor_total: number
  cliente_vinculado_id?: string
}

export default function PagantesPage() {
  const { data: notas = [], isLoading } = useQuery({
    queryKey: ['notas-fiscais-all'],
    queryFn: async () => {
      const resp = await fetch('/api/fiscal/notas')
      if (!resp.ok) throw new Error('Falha ao carregar NFs')
      return resp.json() as Promise<NotaFiscalOut[]>
    },
  })

  const pagantesMap: Record<string, Pagante> = {}
  notas.forEach((nf: NotaFiscalOut) => {
    if (!nf.tomador_nome) return
    const chave = `${nf.tomador_cpf_cnpj}|${nf.tomador_nome}`
    if (!pagantesMap[chave]) {
      pagantesMap[chave] = {
        cpf_cnpj: nf.tomador_cpf_cnpj,
        nome: nf.tomador_nome,
        email: nf.tomador_email,
        nfs: [],
        valor_total: 0,
        cliente_vinculado_id: nf.cliente_id,
      }
    }
    pagantesMap[chave].nfs.push(nf)
    pagantesMap[chave].valor_total += nf.valor_servicos || 0
  })

  const lista: Pagante[] = Object.values(pagantesMap).sort((a, b) => b.valor_total - a.valor_total)

  if (isLoading) return <div style={{ padding: 20 }}>Carregando…</div>

  return (
    <div style={{ padding: 20 }}>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: '#0f766e' }}>
        Pagantes (pessoas que emitiram NF)
      </div>

      {lista.length === 0 ? (
        <p style={{ fontSize: 12, color: '#6b7280', marginTop: 12 }}>Nenhuma NF emitida ainda.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #d1d5db', background: '#f9fafb' }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Nome</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>CPF/CNPJ</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Email</th>
              <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>NFs</th>
              <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>Valor total</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Vínculo</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.cpf_cnpj + p.nome} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>{p.nome}</td>
                <td style={{ padding: '10px 12px', fontSize: 12, color: '#6b7280' }}>
                  {p.cpf_cnpj ? p.cpf_cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4') : '—'}
                </td>
                <td style={{ padding: '10px 12px', fontSize: 12, color: '#6b7280' }}>{p.email || '—'}</td>
                <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>{p.nfs.length}</td>
                <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>{fmtBRL(p.valor_total)}</td>
                <td style={{ padding: '10px 12px', fontSize: 12 }}>
                  {p.cliente_vinculado_id ? (
                    <span style={{ background: '#dcfce7', color: '#15803d', padding: '2px 8px', borderRadius: 4 }}>
                      Vinculado
                    </span>
                  ) : (
                    <span style={{ color: '#9ca3af' }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p style={{ fontSize: 12, color: '#6b7280', marginTop: 16 }}>
        Pagantes são pessoas (CPF/CNPJ) contra quem você emitiu NF-e. Novos pagadores aparecem automaticamente.
        Clientes pré-cadastrados mostram "Vinculado" se a NF foi organizada sob um cliente.
      </p>
    </div>
  )
}
