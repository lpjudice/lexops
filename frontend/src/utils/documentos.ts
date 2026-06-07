// Validação e formatação de CPF/CNPJ + moeda

export function soDigitos(v: string): string {
  return (v || '').replace(/\D/g, '')
}

export function validaCPF(cpf: string): boolean {
  const c = soDigitos(cpf)
  if (c.length !== 11 || /^(\d)\1{10}$/.test(c)) return false
  for (const t of [9, 10]) {
    let soma = 0
    for (let i = 0; i < t; i++) soma += parseInt(c[i]) * (t + 1 - i)
    let dig = (soma * 10) % 11
    if (dig === 10) dig = 0
    if (dig !== parseInt(c[t])) return false
  }
  return true
}

export function soAlfanum(v: string): string {
  return (v || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase()
}

/** Valida CNPJ numérico OU alfanumérico (vigente a partir de 2026). */
export function validaCNPJ(cnpj: string): boolean {
  const c = soAlfanum(cnpj)
  if (c.length !== 14 || /^(.)\1{13}$/.test(c)) return false
  if (!/^[0-9A-Z]{12}\d{2}$/.test(c)) return false
  const val = (ch: string) => ch.charCodeAt(0) - 48  // 0-9→0-9, A-Z→17-42
  const calc = (len: number) => {
    const pesos = len === 12
      ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
      : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    let soma = 0
    for (let i = 0; i < len; i++) soma += val(c[i]) * pesos[i]
    const r = soma % 11
    return r < 2 ? 0 : 11 - r
  }
  return calc(12) === parseInt(c[12]) && calc(13) === parseInt(c[13])
}

/** Valida CPF (11) ou CNPJ (14). Retorna {valido, tipo}. */
export function validaDocumento(doc: string): { valido: boolean; tipo: 'CPF' | 'CNPJ' | '' } {
  const a = soAlfanum(doc)
  if (a.length === 11 && /^\d+$/.test(a)) return { valido: validaCPF(a), tipo: 'CPF' }
  if (a.length === 14) return { valido: validaCNPJ(a), tipo: 'CNPJ' }
  return { valido: false, tipo: '' }
}

/** Máscara dinâmica: CPF ###.###.###-## ou CNPJ ##.###.###/####-## (aceita letras no CNPJ). */
export function mascaraDocumento(v: string): string {
  const a = soAlfanum(v).slice(0, 14)
  // CPF só com 11 dígitos numéricos
  if (a.length <= 11 && /^\d*$/.test(a)) {
    return a
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d{1,2})$/, '$1-$2')
  }
  // CNPJ (numérico ou alfanumérico): ##.###.###/####-##
  return a
    .replace(/^([0-9A-Z]{2})([0-9A-Z])/, '$1.$2')
    .replace(/^([0-9A-Z]{2}\.[0-9A-Z]{3})([0-9A-Z])/, '$1.$2')
    .replace(/^([0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3})([0-9A-Z])/, '$1/$2')
    .replace(/(\/[0-9A-Z]{4})(\d{1,2})$/, '$1-$2')
}

/** Máscara de telefone: (##) #####-#### */
export function mascaraTelefone(v: string): string {
  const d = soDigitos(v).slice(0, 11)
  if (d.length <= 10) {
    return d.replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{4})(\d{1,4})$/, '$1-$2')
  }
  return d.replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{5})(\d{1,4})$/, '$1-$2')
}

/** Formata número como moeda BRL: 1234.5 → "1.234,50" (sem o R$). */
export function formataMoeda(n: number): string {
  if (n == null || isNaN(n)) return ''
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** "1.234,50" → 1234.5 */
export function parseMoeda(s: string): number {
  return parseFloat((s || '').replace(/\./g, '').replace(',', '.')) || 0
}
