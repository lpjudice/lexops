import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import { usuariosApi, type Usuario, type UsuarioCreate, type UsuarioUpdate } from '../api/usuarios'
import { useAuth } from '../contexts/AuthContext'
import styles from './Page.module.css'
import cfg from './ConfiguracoesPage.module.css'

const DEFAULT_PASTA = '/Users/lucasjudice/Dropbox/Clientes/LexOps'
const PASTA_KEY = 'gestor_pasta_clientes'

function usePastaClientes() {
  const [pasta, setPastaState] = useState(() =>
    localStorage.getItem(PASTA_KEY) || DEFAULT_PASTA
  )
  const setPasta = (v: string) => {
    localStorage.setItem(PASTA_KEY, v)
    setPastaState(v)
  }
  return [pasta, setPasta] as const
}

function useGoogleStatus() {
  return useQuery({
    queryKey: ['google-status'],
    queryFn: () => api.get<{ conectado: boolean; email: string | null }>('/auth/google/status').then((r) => r.data),
    refetchInterval: 30_000,
  })
}

const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  membro: 'Membro',
}
const ROLE_COLORS: Record<string, string> = {
  super_admin: cfg.roleSuperAdmin,
  admin: cfg.roleAdmin,
  membro: cfg.roleMembro,
}

const EMPTY_CREATE: UsuarioCreate = {
  email: '',
  nome: '',
  role: 'membro',
  pode_ver_financeiro: true,
  pode_ver_contratos: true,
  pode_ver_tarefas_outros: true,
  clientes_restritos: false,
}

function MembrosSection() {
  const qc = useQueryClient()
  const { usuario: me, isSuperAdmin, isAdmin } = useAuth()
  const { data: usuarios = [] } = useQuery({
    queryKey: ['usuarios'],
    queryFn: usuariosApi.listar,
  })
  const [novoForm, setNovoForm] = useState<UsuarioCreate>(EMPTY_CREATE)
  const [criando, setCriando] = useState(false)
  const [editando, setEditando] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<UsuarioUpdate>({})

  const criar = useMutation({
    mutationFn: (d: UsuarioCreate) => usuariosApi.criar(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['usuarios'] }); setCriando(false); setNovoForm(EMPTY_CREATE) },
  })
  const reenviar = useMutation({
    mutationFn: (id: string) => usuariosApi.reenviarConvite(id),
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UsuarioUpdate }) => usuariosApi.atualizar(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['usuarios'] }); setEditando(null) },
  })
  const deletar = useMutation({
    mutationFn: usuariosApi.deletar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['usuarios'] }),
  })

  if (!isAdmin) return null

  return (
    <div className={cfg.secao}>
      <div className={cfg.secaoHeader}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 className={cfg.secaoTitulo}>Controle de Acesso</h2>
            <p className={cfg.secaoDesc}>
              Gerencie usuários e perfis de acesso ao sistema.
            </p>
          </div>
          {isSuperAdmin && (
            <button className={styles.btnPrimary} style={{ fontSize: 12, padding: '6px 14px' }} onClick={() => setCriando(true)}>
              + Novo membro
            </button>
          )}
        </div>
      </div>

      {/* Form de criação */}
      {criando && (
        <div className={cfg.novoForm}>
          <h3 className={cfg.novoFormTitulo}>Novo membro</h3>
          <div className={cfg.novoFormGrid}>
            <div className={cfg.novoFormField}>
              <label className={cfg.novoFormLabel}>Nome</label>
              <input className={styles.input} value={novoForm.nome} onChange={e => setNovoForm({ ...novoForm, nome: e.target.value })} placeholder="Nome completo" />
            </div>
            <div className={cfg.novoFormField}>
              <label className={cfg.novoFormLabel}>Email</label>
              <input className={styles.input} type="email" value={novoForm.email} onChange={e => setNovoForm({ ...novoForm, email: e.target.value })} placeholder="email@escritorio.com.br" />
            </div>
            <div className={cfg.novoFormField}>
              <label className={cfg.novoFormLabel}>Perfil</label>
              <select className={styles.input} value={novoForm.role} onChange={e => setNovoForm({ ...novoForm, role: e.target.value })}>
                <option value="membro">Membro</option>
                <option value="admin">Admin</option>
                {isSuperAdmin && <option value="super_admin">Super Admin</option>}
              </select>
            </div>
          </div>
          <div className={cfg.permissoesRow}>
            <label className={cfg.permLabel}><input type="checkbox" checked={novoForm.pode_ver_financeiro} onChange={e => setNovoForm({ ...novoForm, pode_ver_financeiro: e.target.checked })} /> Ver Financeiro</label>
            <label className={cfg.permLabel}><input type="checkbox" checked={novoForm.pode_ver_contratos} onChange={e => setNovoForm({ ...novoForm, pode_ver_contratos: e.target.checked })} /> Ver Contratos</label>
            <label className={cfg.permLabel}><input type="checkbox" checked={novoForm.pode_ver_tarefas_outros} onChange={e => setNovoForm({ ...novoForm, pode_ver_tarefas_outros: e.target.checked })} /> Ver tarefas de outros</label>
          </div>
          <div style={{ display: 'flex', gap: 8, padding: '0 24px 20px' }}>
            <button className={styles.btnPrimary} style={{ fontSize: 12 }} onClick={() => criar.mutate(novoForm)} disabled={!novoForm.nome || !novoForm.email || criar.isPending}>
              Criar
            </button>
            <button className={styles.btnDanger} onClick={() => setCriando(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {/* Lista de usuários */}
      <div className={cfg.usuariosList}>
        {usuarios.map((u) => {
          const isMe = u.id === me?.id
          const isEditing = editando === u.id
          return (
            <div key={u.id} className={`${cfg.usuarioCard} ${!u.ativo ? cfg.usuarioInativo : ''}`}>
              <div className={cfg.usuarioHeader}>
                <div className={cfg.usuarioBadge}>
                  {u.nome.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()}
                </div>
                <div className={cfg.usuarioInfo}>
                  <div className={cfg.usuarioNome}>
                    {u.nome}
                    {isMe && <span className={cfg.voceTag}>você</span>}
                    {!u.ativo && <span className={cfg.inativoTag}>inativo</span>}
                  </div>
                  <div className={cfg.usuarioEmail}>{u.email}</div>
                </div>
                <span className={`${cfg.roleTag} ${ROLE_COLORS[u.role] ?? ''}`}>
                  {ROLE_LABELS[u.role] ?? u.role}
                </span>
                {isSuperAdmin && !isMe && (
                  <div className={cfg.usuarioAcoes}>
                    {!u.ativo && (
                      <button className={cfg.btnEdit} onClick={() => reenviar.mutate(u.id)} disabled={reenviar.isPending}>
                        Reenviar convite
                      </button>
                    )}
                    <button className={cfg.btnEdit} onClick={() => {
                      setEditando(u.id)
                      setEditForm({ nome: u.nome, role: u.role, ativo: u.ativo, pode_ver_financeiro: u.pode_ver_financeiro, pode_ver_contratos: u.pode_ver_contratos, pode_ver_tarefas_outros: u.pode_ver_tarefas_outros })
                    }}>Editar</button>
                    {u.role !== 'super_admin' && (
                      <button className={styles.btnDanger} onClick={() => { if (confirm(`Remover ${u.nome}?`)) deletar.mutate(u.id) }}>Remover</button>
                    )}
                  </div>
                )}
              </div>

              {/* Permissões chip row */}
              {!isEditing && (
                <div className={cfg.permChips}>
                  <span className={u.pode_ver_financeiro ? cfg.chipOn : cfg.chipOff}>Financeiro</span>
                  <span className={u.pode_ver_contratos ? cfg.chipOn : cfg.chipOff}>Contratos</span>
                  <span className={u.pode_ver_tarefas_outros ? cfg.chipOn : cfg.chipOff}>Tarefas de outros</span>
                  {u.clientes_restritos && <span className={cfg.chipWarn}>Clientes restritos</span>}
                </div>
              )}

              {/* Edit form inline */}
              {isEditing && (
                <div className={cfg.editInline}>
                  <div className={cfg.novoFormGrid}>
                    <div className={cfg.novoFormField}>
                      <label className={cfg.novoFormLabel}>Nome</label>
                      <input className={styles.input} value={editForm.nome ?? ''} onChange={e => setEditForm({ ...editForm, nome: e.target.value })} />
                    </div>
                    <div className={cfg.novoFormField}>
                      <label className={cfg.novoFormLabel}>Perfil</label>
                      <select className={styles.input} value={editForm.role ?? 'membro'} onChange={e => setEditForm({ ...editForm, role: e.target.value })}>
                        <option value="membro">Membro</option>
                        <option value="admin">Admin</option>
                        {isSuperAdmin && <option value="super_admin">Super Admin</option>}
                      </select>
                    </div>
                    <div className={cfg.novoFormField}>
                      <label className={cfg.novoFormLabel}>Nova senha (opcional)</label>
                      <input className={styles.input} type="text" placeholder="Deixe vazio para manter" onChange={e => setEditForm({ ...editForm, senha: e.target.value || undefined })} />
                    </div>
                  </div>
                  <div className={cfg.permissoesRow}>
                    <label className={cfg.permLabel}><input type="checkbox" checked={editForm.ativo ?? true} onChange={e => setEditForm({ ...editForm, ativo: e.target.checked })} /> Ativo</label>
                    <label className={cfg.permLabel}><input type="checkbox" checked={editForm.pode_ver_financeiro ?? true} onChange={e => setEditForm({ ...editForm, pode_ver_financeiro: e.target.checked })} /> Ver Financeiro</label>
                    <label className={cfg.permLabel}><input type="checkbox" checked={editForm.pode_ver_contratos ?? true} onChange={e => setEditForm({ ...editForm, pode_ver_contratos: e.target.checked })} /> Ver Contratos</label>
                    <label className={cfg.permLabel}><input type="checkbox" checked={editForm.pode_ver_tarefas_outros ?? true} onChange={e => setEditForm({ ...editForm, pode_ver_tarefas_outros: e.target.checked })} /> Ver tarefas de outros</label>
                  </div>
                  <div style={{ display: 'flex', gap: 8, padding: '0 24px 20px' }}>
                    <button className={styles.btnPrimary} style={{ fontSize: 12 }} onClick={() => atualizar.mutate({ id: u.id, data: editForm })}>Salvar</button>
                    <button className={styles.btnDanger} onClick={() => setEditando(null)}>Cancelar</button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ConfiguracoesPage() {
  const [searchParams] = useSearchParams()
  const conviteBanner = searchParams.get('convite') === '1'
  const { data: googleStatus } = useGoogleStatus()
  const [pastaClientes, setPastaClientes] = usePastaClientes()
  const [editandoPasta, setEditandoPasta] = useState(false)
  const [pastaEdit, setPastaEdit] = useState(pastaClientes)
  const [copiado, setCopiado] = useState(false)
  const conectado = googleStatus?.conectado ?? false
  const googleEmail = googleStatus?.email ?? null

  const handleConnectGoogle = () => {
    window.location.href = '/api/auth/google'
  }

  const copiarPasta = () => {
    navigator.clipboard.writeText(pastaClientes).then(() => {
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    })
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Configurações</h1>
      </div>

      {conviteBanner && (
        <div className={cfg.conviteBanner}>
          <div className={cfg.conviteBannerIcon}>G</div>
          <div className={cfg.conviteBannerTexto}>
            <strong>Conecte sua conta Google para habilitar Gmail e Google Calendar.</strong>
            <span> Use a conta <code>@pimentajudice.com.br</code> para ter acesso completo às integrações do escritório.</span>
          </div>
          <button className={styles.btnPrimary} style={{ whiteSpace: 'nowrap', fontSize: 13 }} onClick={() => { window.location.href = '/api/auth/google' }}>
            Conectar Google →
          </button>
        </div>
      )}

      <div className={cfg.secoes}>
        {/* Seção: Controle de Acesso */}
        <MembrosSection />

        {/* Seção: Google */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Integrações Google</h2>
            <p className={cfg.secaoDesc}>
              Conecte sua conta Google para habilitar sincronização de emails (Gmail) e criação de eventos no calendário (Google Calendar).
            </p>
          </div>

          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>G</div>
              <div>
                <div className={cfg.itemNome}>Conta Google</div>
                <div className={cfg.itemStatus}>
                  {conectado ? (
                    <>
                      <span className={cfg.statusOk}>● Conectado — Gmail e Calendar ativos</span>
                      {googleEmail && <div className={cfg.contaEmail}>{googleEmail}</div>}
                    </>
                  ) : (
                    <span className={cfg.statusOff}>● Desconectado — clique para autorizar</span>
                  )}
                </div>
              </div>
            </div>
            <button
              className={conectado ? cfg.btnReconectar : styles.btnPrimary}
              onClick={handleConnectGoogle}
            >
              {conectado ? 'Reconectar' : 'Conectar Google'}
            </button>
          </div>
        </div>

        {/* Seção: IAs */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Modelos de IA</h2>
            <p className={cfg.secaoDesc}>
              As chaves de API são configuradas via variáveis de ambiente no servidor.
            </p>
          </div>
          <div className={cfg.modelosGrid}>
            <div className={cfg.modeloCard}>
              <div className={cfg.modeloNome}>Claude (Anthropic)</div>
              <div className={cfg.modeloModelo}>claude-opus-4-5</div>
              <div className={cfg.modeloUso}>Análise de processos, documentos PDF</div>
            </div>
            <div className={cfg.modeloCard}>
              <div className={cfg.modeloNome}>GPT-4o (OpenAI)</div>
              <div className={cfg.modeloModelo}>gpt-4o</div>
              <div className={cfg.modeloUso}>Chat de clientes, assistência geral</div>
            </div>
            <div className={cfg.modeloCard}>
              <div className={cfg.modeloNome}>Gemini (Google)</div>
              <div className={cfg.modeloModelo}>gemini-2.5-flash</div>
              <div className={cfg.modeloUso}>Teses IA, sugestões jurídicas</div>
            </div>
          </div>
        </div>

        {/* Seção: Pasta de Clientes */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Pasta Local de Clientes</h2>
            <p className={cfg.secaoDesc}>
              Pasta raiz onde ficam as subpastas dos clientes (Contratos/, IA/, Reembolsos/, etc).
              Clique em "Abrir no Finder" para acessar diretamente.
            </p>
          </div>
          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>📁</div>
              <div>
                <div className={cfg.itemNome}>Diretório Base</div>
                {editandoPasta ? (
                  <input
                    style={{ fontSize: 12, fontFamily: 'monospace', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 8px', width: 400 }}
                    value={pastaEdit}
                    onChange={(e) => setPastaEdit(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { setPastaClientes(pastaEdit); setEditandoPasta(false) }
                      if (e.key === 'Escape') setEditandoPasta(false)
                    }}
                    autoFocus
                  />
                ) : (
                  <code style={{ fontSize: 12, color: '#6b7280' }}>{pastaClientes}</code>
                )}
              </div>
            </div>
            {editandoPasta ? (
              <div style={{ display: 'flex', gap: 6 }}>
                <button className={styles.btnPrimary} style={{ fontSize: 12, padding: '5px 14px' }}
                  onClick={() => { setPastaClientes(pastaEdit); setEditandoPasta(false) }}>
                  Salvar
                </button>
                <button className={styles.btnDanger} onClick={() => setEditandoPasta(false)}>Cancelar</button>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className={cfg.btnAbrirPasta}
                  onClick={copiarPasta}
                  title="Copia o caminho — cole no Finder com Cmd+Shift+G"
                >
                  {copiado ? '✓ Copiado!' : '↗ Abrir no Finder'}
                </button>
                <button className={cfg.btnReconectar}
                  onClick={() => { setPastaEdit(pastaClientes); setEditandoPasta(true) }}>
                  Editar
                </button>
              </div>
            )}
          </div>
          {copiado && (
            <div style={{ fontSize: 11, color: '#6b7280', paddingLeft: 4 }}>
              Caminho copiado — abra o Finder e use <kbd style={{ background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 3, padding: '1px 5px' }}>Cmd+Shift+G</kbd> para navegar.
            </div>
          )}
        </div>

        {/* Seção: Sistema */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Sistema</h2>
          </div>
          <div className={cfg.infoGrid}>
            <div className={cfg.infoItem}>
              <span className={cfg.infoLabel}>Versão</span>
              <span className={cfg.infoValor}>Gestor Jurídico v1.0</span>
            </div>
            <div className={cfg.infoItem}>
              <span className={cfg.infoLabel}>Escritório</span>
              <span className={cfg.infoValor}>Pimenta Judice Advogados</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
