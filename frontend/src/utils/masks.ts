// Máscaras de campos cadastrais brasileiros, compartilhadas entre o cadastro
// interno (ClientesPage) e o formulário público de autocadastro.

export function maskCPF(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 3) return d
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
}

export function maskCNPJ(v: string) {
  // CNPJ pode ser alfanumérico (nova regra 2026), mas mantemos a formatação posicional
  const d = v.replace(/[^a-zA-Z0-9]/g, '').slice(0, 14).toUpperCase()
  if (d.length <= 2) return d
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`
  if (d.length <= 8) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`
  if (d.length <= 12) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8)}`
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
}

export function maskTelefone(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 2) return d.length ? `(${d}` : ''
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

export function maskCEP(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 8)
  if (d.length <= 5) return d
  return `${d.slice(0, 5)}-${d.slice(5)}`
}

export function applyDocMask(v: string, tipo: 'PF' | 'PJ') {
  return tipo === 'PF' ? maskCPF(v) : maskCNPJ(v)
}

export const ESTADO_CIVIL_OPCOES = [
  'Solteiro(a)',
  'Casado(a)',
  'Divorciado(a)',
  'Viúvo(a)',
  'União estável',
  'Separado(a) judicialmente',
]

export interface ViaCepResult {
  logradouro?: string
  bairro?: string
  localidade?: string
  uf?: string
  erro?: boolean
}

/** Consulta o ViaCEP (API pública) e devolve os campos de endereço, ou null. */
export async function buscarCep(cep: string): Promise<ViaCepResult | null> {
  const digits = cep.replace(/\D/g, '')
  if (digits.length !== 8) return null
  try {
    const resp = await fetch(`https://viacep.com.br/ws/${digits}/json/`)
    if (!resp.ok) return null
    const data = (await resp.json()) as ViaCepResult
    if (data.erro) return null
    return data
  } catch {
    return null
  }
}
