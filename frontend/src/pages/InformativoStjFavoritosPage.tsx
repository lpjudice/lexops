import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Star } from 'lucide-react'
import { informativoStjApi } from '../api/informativoStj'
import { ramoCor } from '../utils/ramoColor'
import styles from './InformativoStjEdicaoPage.module.css'
import listaStyles from './InformativoStjPage.module.css'

export default function InformativoStjFavoritosPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: itens = [], isLoading } = useQuery({
    queryKey: ['informativo-stj', 'favoritos'],
    queryFn: () => informativoStjApi.listarFavoritos(),
  })

  const favoritar = useMutation({
    mutationFn: (itemId: string) => informativoStjApi.favoritar(itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj', 'favoritos'] }),
  })

  return (
    <div>
      <button className={styles.voltar} onClick={() => navigate('/informativo-stj')}>
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
            onClick={() => navigate(`/informativo-stj/${item.edicao_id}`)}
          >
            <div className={styles.verbeteHead}>
              <div className={styles.verbeteHeadLeft}>
                <div className={styles.verbeteTitulo}>{item.titulo}</div>
                <div className={styles.verbeteDestaqueOficial}>
                  {item.resumo_tema_central || item.destaque_oficial}
                </div>
                <div className={styles.verbeteMeta}>
                  <span className={styles.pill} style={{ background: cor.bg, color: cor.fg }}>
                    {item.ramo_direito}
                  </span>
                </div>
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
