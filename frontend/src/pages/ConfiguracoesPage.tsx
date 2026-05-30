import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import { tarefasApi } from '../api/tarefas'
import { reunioesApi } from '../api/reunioes'
import { usuariosApi, type UsuarioCreate, type UsuarioUpdate } from '../api/usuarios'
import { useAuth } from '../contexts/AuthContext'
import styles from './Page.module.css'
import cfg from './ConfiguracoesPage.module.css'

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

interface AcessoItem {
  tipo: 'tarefa' | 'reuniao' | 'anotacao'
  titulo: string
  usuarios: { id: string; nome: string }[]
  id: string
}

interface AcessoGrupo {
  cliente_nome: string
  itens: AcessoItem[]
}

function AcessosConfidenciaisSection() {
  const qc = useQueryClient()

  const { data: grupos = [], isLoading, refetch } = useQuery({
    queryKey: ['acesso-confidencial'],
    queryFn: () => api.get<AcessoGrupo[]>('/system/acesso-confidencial').then((r) => r.data),
  })

  const revogarTarefa = useMutation({
    mutationFn: ({ id, uid }: { id: string; uid: string }) => tarefasApi.revogarAcesso(id, uid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['acesso-confidencial'] }); refetch() },
  })

  const revogarReuniao = useMutation({
    mutationFn: ({ id, uid }: { id: string; uid: string }) => reunioesApi.revogarAcesso(id, uid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['acesso-confidencial'] }); refetch() },
  })

  const TIPO_LABEL: Record<string, string> = {
    tarefa: 'Tarefa',
    reuniao: 'Reunião',
    anotacao: 'Anotação',
  }

  const handleRevogar = (item: AcessoItem, uid: string) => {
    if (item.tipo === 'tarefa') revogarTarefa.mutate({ id: item.id, uid })
    else if (item.tipo === 'reuniao') revogarReuniao.mutate({ id: item.id, uid })
    else alert('Revogação de anotações não disponível aqui.')
  }

  return (
    <div className={cfg.secao}>
      <div className={cfg.secaoHeader}>
        <h2 className={cfg.secaoTitulo}>Acessos Confidenciais</h2>
        <p className={cfg.secaoDesc}>
          Visão geral de quem tem acesso a itens confidenciais por cliente.
        </p>
      </div>

      {isLoading ? (
        <div style={{ padding: '16px 24px', fontSize: 13, color: '#6b7280' }}>Carregando...</div>
      ) : grupos.length === 0 ? (
        <div style={{ padding: '16px 24px', fontSize: 13, color: '#9ca3af' }}>Nenhum acesso confidencial concedido.</div>
      ) : (
        <div>
          {grupos.map((grupo) => (
            <div key={grupo.cliente_nome} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <div style={{ padding: '10px 24px 4px', fontSize: 12, fontWeight: 700, color: '#374151', background: '#f9fafb', letterSpacing: '0.03em' }}>
                {grupo.cliente_nome}
              </div>
              {grupo.itens.map((item) => (
                <div key={item.id} style={{ padding: '8px 24px 8px 32px', borderTop: '1px solid #f3f4f6' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 600, background: '#ede9fe', color: '#6d28d9', borderRadius: 4, padding: '1px 6px', whiteSpace: 'nowrap' }}>
                      {TIPO_LABEL[item.tipo] ?? item.tipo}
                    </span>
                    <span style={{ fontSize: 13, color: '#1d1e20', fontWeight: 500 }}>{item.titulo}</span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {item.usuarios.map((u) => (
                      <span key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, background: '#f3f4f6', borderRadius: 4, padding: '2px 8px' }}>
                        <span style={{ color: '#374151' }}>{u.nome}</span>
                        <button
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', fontSize: 13, lineHeight: 1, padding: '0 2px' }}
                          onClick={() => handleRevogar(item, u.id)}
                          title="Revogar acesso"
                        >×</button>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ConfiguracoesPage() {
  const [searchParams] = useSearchParams()
  const conviteBanner = searchParams.get('convite') === '1'
  const googleMasterResult = searchParams.get('google')
  const googleUserResult = searchParams.get('google_user') // 'conectado' | 'erro' | null
  const googleUserExtraResult = searchParams.get('google_user_extra') // 'conectado' | 'erro' | null
  const { data: googleStatus } = useGoogleStatus()
  const { usuario: me, isSuperAdmin, refreshMe } = useAuth()

  // Refresh me after Google OAuth callback so google_email updates immediately
  useEffect(() => {
    if (googleUserResult === 'conectado' || googleUserExtraResult === 'conectado') {
      refreshMe()
    }
  }, [googleUserResult, googleUserExtraResult]) // eslint-disable-line react-hooks/exhaustive-deps

  const conectado = googleStatus?.conectado ?? false
  const googleEmail = googleStatus?.email ?? null

  const handleConnectGoogle = () => {
    window.location.href = '/api/auth/google'
  }

  const handleConnectPersonalGoogle = () => {
    if (!me) return
    window.location.href = `/api/auth/google/user?usuario_id=${me.id}`
  }

  const handleDisconnectPersonalGoogle = async () => {
    if (!me) return
    await api.delete(`/auth/google/user?usuario_id=${me.id}`)
    await refreshMe()
  }

  const handleConnectExtraGoogle = () => {
    if (!me) return
    window.location.href = `/api/auth/google/user/extra?usuario_id=${me.id}`
  }

  const handleDisconnectExtraGoogle = async () => {
    if (!me) return
    await api.delete(`/auth/google/user/extra?usuario_id=${me.id}`)
    await refreshMe()
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
      {googleUserResult === 'conectado' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerSucesso}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Conta Google pessoal conectada com sucesso!</strong>
            <span> Agora você pode sincronizar emails dos seus clientes.</span>
          </div>
        </div>
      )}
      {googleMasterResult === 'conectado' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerSucesso}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Conta Google master conectada com sucesso!</strong>
            <span> A integração global do escritório ficou ativa para todos os usuários da plataforma.</span>
          </div>
        </div>
      )}
      {googleMasterResult === 'erro' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerErro}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Erro ao conectar a conta Google master.</strong>
            <span> Tente novamente com um super admin.</span>
          </div>
        </div>
      )}
      {googleUserResult === 'erro' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerErro}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Erro ao conectar conta Google.</strong>
            <span> Tente novamente.</span>
          </div>
        </div>
      )}
      {googleUserExtraResult === 'conectado' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerSucesso}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Conta Google extra conectada com sucesso!</strong>
            <span> Os emails dessa conta também serão incluídos na busca por clientes.</span>
          </div>
        </div>
      )}
      {googleUserExtraResult === 'erro' && (
        <div className={`${cfg.conviteBanner} ${cfg.bannerErro}`}>
          <div className={cfg.conviteBannerTexto}>
            <strong>Erro ao conectar conta Google extra.</strong>
            <span> Tente novamente.</span>
          </div>
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
              Esta é a conta global do escritório. Quando conectada por um super admin, ela fica disponível para toda a plataforma, incluindo Gmail, Calendar e Drive.
            </p>
          </div>

          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>G</div>
              <div>
                <div className={cfg.itemNome}>Conta Google Master</div>
                <div className={cfg.itemStatus}>
                  {conectado ? (
                    <>
                      <span className={cfg.statusOk}>● Conectado — integração global ativa</span>
                      {googleEmail && <div className={cfg.contaEmail}>{googleEmail}</div>}
                    </>
                  ) : (
                    <span className={cfg.statusOff}>● Desconectado</span>
                  )}
                </div>
              </div>
            </div>
            {isSuperAdmin && (
              <button
                className={conectado ? cfg.btnReconectar : styles.btnPrimary}
                onClick={handleConnectGoogle}
              >
                {conectado ? 'Reconectar' : 'Conectar Google'}
              </button>
            )}
          </div>
        </div>

        {/* Seção: Google pessoal */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Minha Conta Google</h2>
            <p className={cfg.secaoDesc}>
              Conecte sua conta pessoal do escritório para sincronizar emails trocados com clientes.
              Cada membro pode conectar a sua própria conta, além de uma conta extra opcional.
            </p>
          </div>
          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>G</div>
              <div>
                <div className={cfg.itemNome}>Conta pessoal</div>
                <div className={cfg.itemStatus}>
                  {me?.google_email ? (
                    <>
                      <span className={cfg.statusOk}>● Conectado</span>
                      <div className={cfg.contaEmail}>{me.google_email}</div>
                    </>
                  ) : (
                    <span className={cfg.statusOff}>● Não conectado</span>
                  )}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className={me?.google_email ? cfg.btnReconectar : styles.btnPrimary} onClick={handleConnectPersonalGoogle}>
                {me?.google_email ? 'Reconectar' : 'Conectar minha conta'}
              </button>
              {me?.google_email && (
                <button className={styles.btnDanger} onClick={handleDisconnectPersonalGoogle}>
                  Desconectar
                </button>
              )}
            </div>
          </div>
          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>G</div>
              <div>
                <div className={cfg.itemNome}>Conta extra</div>
                <div className={cfg.itemStatus}>
                  {me?.google_email_extra ? (
                    <>
                      <span className={cfg.statusOk}>● Conectado</span>
                      <div className={cfg.contaEmail}>{me.google_email_extra}</div>
                    </>
                  ) : (
                    <span className={cfg.statusOff}>● Não conectado</span>
                  )}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className={me?.google_email_extra ? cfg.btnReconectar : styles.btnPrimary} onClick={handleConnectExtraGoogle}>
                {me?.google_email_extra ? 'Reconectar' : 'Conectar conta extra'}
              </button>
              {me?.google_email_extra && (
                <button className={styles.btnDanger} onClick={handleDisconnectExtraGoogle}>
                  Desconectar
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Seção: Google Drive */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Google Drive — Lexops</h2>
            <p className={cfg.secaoDesc}>
              Pasta raiz do escritório no Google Drive, onde ficam arquivos de clientes, contratos e reuniões.
            </p>
          </div>
          <div className={cfg.item}>
            <div className={cfg.itemLeft}>
              <div className={cfg.itemIcon}>📂</div>
              <div>
                <div className={cfg.itemNome}>Raiz Lexops / Drive</div>
                <div className={cfg.itemStatus}>
                  {conectado
                    ? <span className={cfg.statusOk}>● Conta master conectada</span>
                    : <span className={cfg.statusOff}>● Conta master não conectada</span>}
                </div>
              </div>
            </div>
            {conectado && (
              <a
                href="https://drive.google.com/drive/my-drive"
                target="_blank"
                rel="noopener noreferrer"
                className={cfg.btnAbrirPasta}
              >
                ↗ Abrir Drive
              </a>
            )}
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

        {/* Seção: Acessos Confidenciais — super_admin only */}
        {isSuperAdmin && <AcessosConfidenciaisSection />}

        {/* Seção: Sistema */}
        <div className={cfg.secao}>
          <div className={cfg.secaoHeader}>
            <h2 className={cfg.secaoTitulo}>Sistema</h2>
          </div>
          <div className={cfg.infoGrid}>
            <div className={cfg.infoItem}>
              <span className={cfg.infoLabel}>Versão</span>
              <span className={cfg.infoValor}>Sui v1.0</span>
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
