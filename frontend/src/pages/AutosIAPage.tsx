import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../api/autosIa'
import styles from './Page.module.css'

export default function AutosIAPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [numeroProcesso, setNumeroProcesso] = useState('')
  const [descricao, setDescricao] = useState('')

  const { data: casos = [], isLoading } = useQuery({
    queryKey: ['autos-ia', 'casos'],
    queryFn: () => autosIa.listarCasos(),
  })

  const criar = useMutation({
    mutationFn: () => autosIa.criarCaso({
      nome,
      numero_processo: numeroProcesso || undefined,
      descricao: descricao || undefined,
    }),
    onSuccess: (caso) => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'casos'] })
      setShowForm(false)
      setNome('')
      setNumeroProcesso('')
      setDescricao('')
      navigate(`/autos-ia/${caso.id}`)
    },
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Autos IA</h1>
          <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: 4 }}>
            Leitura incremental de processos volumosos: suba os autos em blocos e o sistema
            organiza, resume e indexa cada peça automaticamente. Independente do restante do gestor.
          </p>
        </div>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo caso'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate() }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome do caso *</label>
            <input
              className={styles.input}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Ação de Cobrança — Fulano x Beltrano"
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Número do processo (opcional)</label>
            <input
              className={styles.input}
              value={numeroProcesso}
              onChange={(e) => setNumeroProcesso(e.target.value)}
              placeholder="0000000-00.0000.0.00.0000"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição (opcional)</label>
            <textarea
              className={styles.input}
              rows={3}
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
            />
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending || !nome.trim()}>
            {criar.isPending ? 'Criando...' : 'Criar caso'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : casos.length === 0 ? (
        <p className={styles.empty}>Nenhum caso cadastrado ainda.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Caso</th>
                <th>Processo</th>
                <th>Páginas</th>
                <th>Peças</th>
                <th>FAQ</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {casos.map((c) => (
                <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/autos-ia/${c.id}`)}>
                  <td>
                    <strong>{c.nome}</strong>
                    {c.tem_peca_pendente_continuacao && (
                      <span className={styles.badge} style={{ marginLeft: 8, background: '#fef9c3', color: '#a16207' }}>
                        peça em aberto
                      </span>
                    )}
                  </td>
                  <td>{c.numero_processo || '—'}</td>
                  <td>{c.total_paginas}</td>
                  <td>{c.total_pecas}</td>
                  <td>{c.total_perguntas_faq}</td>
                  <td>
                    <span className={`${styles.badge} ${styles[`status_${c.status}`]}`}>{c.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
