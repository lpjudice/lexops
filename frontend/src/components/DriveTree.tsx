/**
 * Árvore navegável dos arquivos vinculados no Google Drive (lazy-load por pasta).
 * Topo = pastas "menu" sob a raiz LexOps. Filtro por mês (modificação/criação).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'

export interface DriveNode {
  id: string
  name: string
  is_folder: boolean
  mime_type: string | null
  size: number
  created_time: string | null
  modified_time: string | null
  web_view_link: string | null
  categoria?: 'cliente' | 'menu' | 'arquivo'
}

type Base = 'modificacao' | 'criacao'

function fetchTree(folderId?: string): Promise<DriveNode[]> {
  return api
    .get<{ itens: DriveNode[] }>('/system/drive/tree', { params: folderId ? { folder_id: folderId } : {} })
    .then((r) => r.data.itens)
}

function fmt(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('pt-BR')
}
function fmtTam(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

interface FiltroCfg { mes: string; base: Base }

/** Arquivos só passam se a data (base) estiver no mês; pastas sempre visíveis (navegação). */
function passaFiltro(node: DriveNode, f: FiltroCfg): boolean {
  if (!f.mes) return true
  if (node.is_folder) return true
  const d = f.base === 'criacao' ? node.created_time : node.modified_time
  return !!d && d.startsWith(f.mes)
}

function Node({ node, filtro, depth }: { node: DriveNode; filtro: FiltroCfg; depth: number }) {
  const [open, setOpen] = useState(false)
  const { data: filhos = [], isLoading } = useQuery({
    queryKey: ['drive-tree', node.id],
    queryFn: () => fetchTree(node.id),
    enabled: node.is_folder && open,
  })

  const rowStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px',
    paddingLeft: 6 + depth * 18, borderRadius: 6, fontSize: 13,
  }
  const filhosFiltrados = filhos.filter((c) => passaFiltro(c, filtro))

  return (
    <div>
      <div style={rowStyle} className="driveRow">
        {node.is_folder ? (
          <button onClick={() => setOpen((o) => !o)}
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 13, width: 16, color: '#6b7280' }}>
            {open ? '▼' : '▶'}
          </button>
        ) : <span style={{ width: 16 }} />}
        <span>{node.is_folder ? (open ? '📂' : '📁') : '📄'}</span>
        {node.web_view_link ? (
          <a href={node.web_view_link} target="_blank" rel="noreferrer"
            style={{ color: node.is_folder ? '#1d1e20' : '#2563eb', textDecoration: 'none', fontWeight: node.is_folder ? 600 : 400 }}>
            {node.name}
          </a>
        ) : <span style={{ fontWeight: node.is_folder ? 600 : 400 }}>{node.name}</span>}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af', whiteSpace: 'nowrap' }}>
          {fmtTam(node.size)} {node.size ? '·' : ''} mod. {fmt(node.modified_time)}
        </span>
      </div>
      {node.is_folder && open && (
        <div>
          {isLoading ? (
            <div style={{ paddingLeft: 24 + depth * 18, fontSize: 12, color: '#9ca3af' }}>Carregando…</div>
          ) : filhosFiltrados.length === 0 ? (
            <div style={{ paddingLeft: 24 + depth * 18, fontSize: 12, color: '#9ca3af' }}>
              {filhos.length === 0 ? '(pasta vazia)' : '(nenhum arquivo no mês filtrado)'}
            </div>
          ) : (
            filhosFiltrados.map((c) => <Node key={c.id} node={c} filtro={filtro} depth={depth + 1} />)
          )}
        </div>
      )}
    </div>
  )
}

export default function DriveTree() {
  const [mes, setMes] = useState('')
  const [base, setBase] = useState<Base>('modificacao')
  const { data: topo = [], isLoading, isError, error } = useQuery({
    queryKey: ['drive-tree', 'root'],
    queryFn: () => fetchTree(),
    retry: false,
  })

  const filtro: FiltroCfg = { mes, base }
  const detail = (error as { response?: { status?: number } })?.response?.status

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 6 }}>
          Filtrar por mês:
          <input type="month" value={mes} onChange={(e) => setMes(e.target.value)}
            style={{ fontSize: 12, padding: '4px 8px', border: '1px solid #e5e7eb', borderRadius: 6 }} />
        </label>
        <select value={base} onChange={(e) => setBase(e.target.value as Base)}
          style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #e5e7eb', borderRadius: 6, color: '#4b5563' }}>
          <option value="modificacao">últimos arquivos adicionados</option>
          <option value="criacao">data de criação</option>
        </select>
        {mes && (
          <button onClick={() => setMes('')} style={{ fontSize: 11, color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
            limpar
          </button>
        )}
      </div>

      {isLoading ? (
        <p style={{ fontSize: 13, color: '#9ca3af' }}>Carregando árvore do Drive…</p>
      ) : isError ? (
        <p style={{ fontSize: 13, color: '#b91c1c' }}>
          {detail === 503 ? 'Google Drive não conectado (conecte a conta master nas Integrações).' : 'Não foi possível carregar a árvore do Drive.'}
        </p>
      ) : topo.length === 0 ? (
        <p style={{ fontSize: 13, color: '#9ca3af' }}>Nenhuma pasta encontrada na raiz do Drive.</p>
      ) : (
        (() => {
          const visiveis = topo.filter((n) => passaFiltro(n, filtro))
          const menus = visiveis.filter((n) => n.categoria !== 'cliente')
          const clientes = visiveis.filter((n) => n.categoria === 'cliente')
          const Grupo = ({ titulo, itens }: { titulo: string; itens: DriveNode[] }) => (
            itens.length === 0 ? null : (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase', color: '#9ca3af', margin: '4px 0 6px 4px' }}>
                  {titulo} <span style={{ color: '#d1d5db' }}>({itens.length})</span>
                </div>
                <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 6 }}>
                  {itens.map((n) => <Node key={n.id} node={n} filtro={filtro} depth={0} />)}
                </div>
              </div>
            )
          )
          return (
            <div style={{ maxHeight: 560, overflowY: 'auto' }}>
              <Grupo titulo="📁 Menus do sistema" itens={menus} />
              <Grupo titulo="👤 Clientes" itens={clientes} />
            </div>
          )
        })()
      )}
    </div>
  )
}
