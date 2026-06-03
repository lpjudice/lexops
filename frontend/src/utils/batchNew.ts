// Estado efêmero (por sessão) da última leitura em lote de andamentos.
//
// Guarda quais processos tiveram andamento novo no lote (e quantos), além do
// link/nome do PDF de relatório gerado. Vive em sessionStorage: some sozinho ao
// fechar a aba/app ("próxima sessão volta tudo azul") e é limpo manualmente ao
// desconectar o token ou ao rodar um novo lote.

const KEY = 'lexops:andamentos-batch'

export interface BatchNewState {
  counts: Record<string, number> // processo_id -> nº de andamentos novos no lote
  drive_link?: string | null
  filename?: string
  at?: string // ISO de quando o lote terminou
}

export function getBatchNew(): BatchNewState | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as BatchNewState
    if (!parsed || typeof parsed !== 'object' || !parsed.counts) return null
    return parsed
  } catch {
    return null
  }
}

export function setBatchNew(state: BatchNewState): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state))
    // Notifica componentes na mesma aba (o evento 'storage' nativo só dispara
    // em outras abas).
    window.dispatchEvent(new Event('batchnew-updated'))
  } catch {
    /* ignore */
  }
}

// Mescla/atualiza campos preservando os counts atuais quando não informados.
export function patchBatchNew(patch: Partial<BatchNewState>): void {
  const cur = getBatchNew()
  setBatchNew({
    counts: patch.counts ?? cur?.counts ?? {},
    drive_link: patch.drive_link ?? cur?.drive_link ?? null,
    filename: patch.filename ?? cur?.filename,
    at: patch.at ?? cur?.at,
  })
}

export function clearBatchNew(): void {
  try {
    sessionStorage.removeItem(KEY)
    window.dispatchEvent(new Event('batchnew-updated'))
  } catch {
    /* ignore */
  }
}
