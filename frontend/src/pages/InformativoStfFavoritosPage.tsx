import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Star } from 'lucide-react'
import { informativoStfApi } from '../api/informativoStf'
import { ramoCor } from '../utils/ramoColor'
import styles from './InformativoStfEdicaoPage.module.css'
import listaStyles from './InformativoStfPage.module.css'

export default function InformativoStfFavoritosPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: itens = [], isLoading } = useQuery({
    queryKey: ['informativo-stf', 'favoritos'],
    queryFn: () => informativoStfApi.listarFavoritos(),
  })

  const favoritar = useMutation({
    mutationFn: (itemId: string) => informativoStfApi.favoritar(itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stf', 'favoritos'] }),
  })

  return (
    <div>
      <button className={styles.voltar} onClick={() => navigate('/informativo-stf')}>
        <ArrowLeft size={14} /> Voltar às edições
      </button>
      <div className={styles.titulo}>Jurisprudência favoritada</div>

      {isLoading && <p>Carregando…</p>}
      {!isLoading && itens.length === 0 && <p className={listaStyles.empty}>Nenhum julgado favoritado ainda.</p>}

      {itens.map((item) => {
        const cor = ramoCor(item.ramo_direito)
        return (
          <div
            key={item.id}
            className={styles.verbete}
            style={{ borderLeftColor: cor.fg, cursor: 'pointer' }}
            onClick={() => navigate(`/informativo-stf/${item.edicao_id}?item=${item.id}`)}
          >
            <div className={styles.verbeteHead}>
              <div className={styles.verbeteHeadLeft}>
                <div className={styles.verbeteMeta}>
                  <span className={styles.pill} style={{ background: cor.bg, color: cor.fg }}>
                    {item.ramo_direito}
                  </span>
                  {item.edicao_numero && <span className={styles.pill}>Informativo nº {item.edicao_numero}</span>}
                </div>
                <div className={styles.verbeteHeadline}>{item.resumo_tema_central || item.destaque_oficial}</div>
                <div className={styles.verbeteTitulo}>{item.titulo}</div>
              </div>
              <button
                className={styles.starBtn}
                onClick={(e) => {
                  e.stopPropagation()
                  favoritar.mutate(item.id)
                }}
                title="Remover dos favoritos"
              >
                <Star size={18} className={styles.starBtnAtivo} fill="currentColor" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
