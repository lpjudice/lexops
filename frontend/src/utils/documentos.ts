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

export function validaCNPJ(cnpj: string): boolean {
  const c = soDigitos(cnpj)
  if (c.length !== 14 || /^(\d)\1{13}$/.test(c)) return false
  const calc = (len: number) => {
    const pesos = len === 12
      ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
      : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    let soma = 0
    for (let i = 0; i < len; i++) soma += parseInt(c[i]) * pesos[i]
    const r = soma % 11
    return r < 2 ? 0 : 11 - r
  }
  return calc(12) === parseInt(c[12]) && calc(13) === parseInt(c[13])
}

/** Valida CPF (11) ou CNPJ (14). Retorna {valido, tipo}. */
export function validaDocumento(doc: string): { valido: boolean; tipo: 'CPF' | 'CNPJ' | '' } {
  const d = soDigitos(doc)
  if (d.length === 11) return { valido: validaCPF(d), tipo: 'CPF' }
  if (d.length === 14) return { valido: validaCNPJ(d), tipo: 'CNPJ' }
  return { valido: false, tipo: '' }
}

/** Máscara dinâmica: CPF ###.###.###-## ou CNPJ ##.###.###/####-## */
export function mascaraDocumento(v: string): string {
  const d = soDigitos(v).slice(0, 14)
  if (d.length <= 11) {
    return d
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d{1,2})$/, '$1-$2')
  }
  return d
    .replace(/(\d{2})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1/$2')
    .replace(/(\d{4})(\d{1,2})$/, '$1-$2')
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
