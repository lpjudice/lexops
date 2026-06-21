import { useQuery } from '@tanstack/react-query'
import { type NotaFiscalOut } from '../api/fiscal'
import { clientesApi, type Cliente } from '../api/clientes'

const fmtBRL = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

interface Endereco {
  logradouro?: string
  numero?: string
  bairro?: string
  cep?: string
  cidade?: string
  estado?: string
  complemento?: string
}

interface Pagante {
  cpf_cnpj: string
  nome: string
  email?: string
  endereco?: Endereco
  nfs: NotaFiscalOut[]
  valor_total: number
  cliente_vinculado_id?: string
  cliente_vinculado_nome?: string
  eh_cliente_cadastrado: boolean
}

export default function PagantesPage() {
  const { data: notas = [], isLoading: notasLoading } = useQuery({
    queryKey: ['notas-fiscais-all'],
    queryFn: async () => {
      const resp = await fetch('/api/fiscal/notas')
      if (!resp.ok) throw new Error('Falha ao carregar NFs')
      return resp.json() as Promise<NotaFiscalOut[]>
    },
  })

  const { data: clientes = [], isLoading: clientesLoading } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const pagantesMap: Record<string, Pagante> = {}
  notas.forEach((nf: NotaFiscalOut) => {
    if (!nf.tomador_nome) return
    const chave = `${nf.tomador_cpf_cnpj}|${nf.tomador_nome}`
    if (!pagantesMap[chave]) {
      // Tenta fazer match com cliente cadastrado pelo CPF/CNPJ
      const clienteMatch = clientes.find(c => c.cpf_cnpj === nf.tomador_cpf_cnpj)
      pagantesMap[chave] = {
        cpf_cnpj: nf.tomador_cpf_cnpj,
        nome: nf.tomador_nome,
        email: nf.tomador_email,
        endereco: nf.tomador_endereco ? {
          logradouro: nf.tomador_endereco.logradouro,
          numero: nf.tomador_endereco.numero,
          bairro: nf.tomador_endereco.bairro,
          cep: nf.tomador_endereco.cep,
          complemento: nf.tomador_endereco.complemento,
        } : undefined,
        nfs: [],
        valor_total: 0,
        cliente_vinculado_id: clienteMatch?.id || nf.cliente_id,
        cliente_vinculado_nome: clienteMatch?.nome,
        eh_cliente_cadastrado: !!clienteMatch,
      }
    }
    pagantesMap[chave].nfs.push(nf)
    pagantesMap[chave].valor_total += nf.valor_servicos || 0
  })

  const lista: Pagante[] = Object.values(pagantesMap).sort((a, b) => b.valor_total - a.valor_total)
  const isLoading = notasLoading || clientesLoading

  if (isLoading) return <div style={{ padding: 20 }}>Carregando…</div>

  function fmtEndereco(e?: Endereco) {
    if (!e) return '—'
    const partes = [e.logradouro, e.numero, e.bairro, e.cep]
      .filter(Boolean)
      .join(' · ')
    return partes || '—'
  }

  return (
    <div style={{ padding: 20 }}>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: '#0f766e' }}>
        Pagantes — Todos contra quem você emitiu NF
      </div>

      {lista.length === 0 ? (
        <p style={{ fontSize: 12, color: '#6b7280', marginTop: 12 }}>Nenhuma NF emitida ainda.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #d1d5db', background: '#f9fafb' }}>
                <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 180 }}>Nome</th>
                <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 130 }}>CPF/CNPJ</th>
                <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 150 }}>Email</th>
                <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 200 }}>Endereço</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>NFs</th>
                <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600, minWidth: 120 }}>Total</th>
                <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 140 }}>Vínculo</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((p) => (
                <tr key={p.cpf_cnpj + p.nome} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#1f2937' }}>{p.nome}</td>
                  <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                    {p.cpf_cnpj
                      ? (p.cpf_cnpj.length === 11
                          ? p.cpf_cnpj.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4')
                          : p.cpf_cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5'))
                      : '—'}
                  </td>
                  <td style={{ padding: '10px 12px', color: '#6b7280', fontSize: 11 }}>{p.email || '—'}</td>
                  <td style={{ padding: '10px 12px', color: '#6b7280', fontSize: 11 }}>{fmtEndereco(p.endereco)}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>{p.nfs.length}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600, color: '#065f46' }}>
                    {fmtBRL(p.valor_total)}
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 11 }}>
                    {p.eh_cliente_cadastrado ? (
                      <span style={{
                        background: '#dcfce7',
                        color: '#15803d',
                        padding: '3px 8px',
                        borderRadius: 4,
                        fontWeight: 600,
                        whiteSpace: 'nowrap'
                      }}>
                        ✓ Cliente: {p.cliente_vinculado_nome || 'Vinculado'}
                      </span>
                    ) : (
                      <span style={{ color: '#9ca3af', fontSize: 10 }}>Não cadastrado</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 20, lineHeight: 1.6 }}>
        <p>
          <strong>Pagantes:</strong> todas as pessoas/empresas contra quem você emitiu NF-e, cadastradas ou não.
        </p>
        <p>
          <strong>Dados:</strong> nome, CPF/CNPJ e endereço conforme preenchido na emissão da NF.
        </p>
        <p>
          <strong>Vínculo:</strong> se o CPF/CNPJ já existe como cliente cadastrado, mostra o nome do cliente.
        </p>
        <p style={{ color: '#9ca3af', fontSize: 11 }}>
          Novos pagantes aparecem automaticamente ao emitir uma NF. Para vincular um pagante a um cliente cadastrado,
          edite o cliente e atualize o CPF/CNPJ, ou emita a próxima NF selecionando o cliente.
        </p>
      </div>
    </div>
  )
}
