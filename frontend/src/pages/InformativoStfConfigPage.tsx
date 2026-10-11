import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { informativoStfApi } from '../api/informativoStf'
import styles from './InformativoStfConfigPage.module.css'

// Ramos do direito como o STF já rotula os verbetes (sem mapeamento próprio).
const AREAS_CONHECIDAS = [
  'Direito Civil',
  'Direito Processual Civil',
  'Direito Tributário',
  'Direito Administrativo',
  'Direito Empresarial',
  'Direito Penal',
  'Direito Processual Penal',
  'Direito Previdenciário',
  'Direito do Consumidor',
  'Direito Constitucional',
  'Direito Falimentar',
  'Direito Eleitoral',
  'Direito Ambiental',
  'Direito Internacional',
]

export default function InformativoStfConfigPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery({
    queryKey: ['informativo-stf', 'config'],
    queryFn: () => informativoStfApi.getConfig(),
  })

  const [areas, setAreas] = useState<string[]>([])
  const [keywords, setKeywords] = useState<string[]>([])
  const [novaKeyword, setNovaKeyword] = useState('')

  useEffect(() => {
    if (config) {
      setAreas(config.areas_selecionadas)
      setKeywords(config.keywords_livres)
    }
  }, [config])

  const salvar = useMutation({
    mutationFn: () => informativoStfApi.updateConfig({ areas_selecionadas: areas, keywords_livres: keywords }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stf', 'config'] }),
  })

  const reclassificar = useMutation({
    mutationFn: () => informativoStfApi.reclassificar(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['informativo-stf'] })
      alert(`${res.alterados} de ${res.total_itens} itens tiveram o destaque reavaliado.`)
    },
  })

  function toggleArea(area: string) {
    setAreas((prev) => (prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]))
  }

  function adicionarKeyword() {
    const v = novaKeyword.trim()
    if (v && !keywords.includes(v)) setKeywords((prev) => [...prev, v])
    setNovaKeyword('')
  }

  if (isLoading) return <p>Carregando…</p>

  return (
    <div>
      <button className={styles.voltar} onClick={() => navigate('/informativo-stf')}>
        <ArrowLeft size={14} /> Voltar às edições
      </button>

      <div className={styles.card}>
        <div className={styles.sectionTitle}>Áreas do direito em destaque</div>
        <div className={styles.sectionHint}>
          Julgados nessas áreas recebem resumo estruturado por IA (tema central + ratio decidendi). As demais mostram
          só o título e o destaque oficial do STF.
        </div>
        <div className={styles.areasGrid}>
          {AREAS_CONHECIDAS.map((area) => (
            <label key={area} className={styles.areaItem}>
              <input type="checkbox" checked={areas.includes(area)} onChange={() => toggleArea(area)} />
              {area}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.sectionTitle}>Palavras-chave livres</div>
        <div className={styles.sectionHint}>
          Além das áreas, destaca qualquer julgado cujo título/destaque contenha uma dessas palavras (ex: "holding",
          "sucessão").
        </div>
        <div className={styles.tagsInput}>
          {keywords.map((kw) => (
            <span key={kw} className={styles.tag}>
              {kw}
              <button onClick={() => setKeywords((prev) => prev.filter((k) => k !== kw))}>×</button>
            </span>
          ))}
          <input
            className={styles.tagInputField}
            value={novaKeyword}
            placeholder="Adicionar palavra-chave…"
            onChange={(e) => setNovaKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                adicionarKeyword()
              }
            }}
            onBlur={adicionarKeyword}
          />
        </div>
      </div>

      <div className={styles.actions}>
        <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => salvar.mutate()} disabled={salvar.isPending}>
          {salvar.isPending ? 'Salvando…' : 'Salvar'}
        </button>
        <button
          className={styles.btn}
          onClick={() => {
            if (confirm('Reclassificar todos os itens existentes com a config atual? Itens recém-destacados entrarão na fila de IA.')) {
              reclassificar.mutate()
            }
          }}
          disabled={reclassificar.isPending}
        >
          {reclassificar.isPending ? 'Reclassificando…' : 'Reclassificar itens existentes'}
        </button>
      </div>
    </div>
  )
}
