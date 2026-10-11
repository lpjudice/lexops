// Paleta fixa e determinística por ramo do direito — mesmo ramo sempre cai na
// mesma cor, sem precisar de mapeamento manual (o STJ usa dezenas de rótulos).
const PALETA = [
  { bg: '#eef2ff', fg: '#4338ca' }, // índigo
  { bg: '#ecfdf5', fg: '#047857' }, // verde
  { bg: '#fef3c7', fg: '#92400e' }, // âmbar
  { bg: '#fce7f3', fg: '#be185d' }, // rosa
  { bg: '#e0f2fe', fg: '#0369a1' }, // azul
  { bg: '#fee2e2', fg: '#b91c1c' }, // vermelho
  { bg: '#f3e8ff', fg: '#7e22ce' }, // violeta
  { bg: '#fff7ed', fg: '#c2410c' }, // laranja
  { bg: '#ecfeff', fg: '#0e7490' }, // ciano
  { bg: '#f0fdf4', fg: '#15803d' }, // esmeralda
  { bg: '#fdf4ff', fg: '#a21caf' }, // magenta
  { bg: '#f1f5f9', fg: '#334155' }, // neutro
]

function hash(str: string): number {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

// Agrupa pelo primeiro ramo citado (o STJ às vezes lista vários separados por vírgula).
export function ramoChave(ramoDireito: string): string {
  return (ramoDireito || '').split(',')[0].trim()
}

export function ramoCor(ramoDireito: string): { bg: string; fg: string } {
  const chave = ramoChave(ramoDireito)
  if (!chave) return PALETA[PALETA.length - 1]
  return PALETA[hash(chave) % PALETA.length]
}
