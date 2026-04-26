const TJ_BY_CODE: Record<string, string> = {
  '01': 'TJAC',
  '02': 'TJAL',
  '03': 'TJAP',
  '04': 'TJAM',
  '05': 'TJBA',
  '06': 'TJCE',
  '07': 'TJDFT',
  '08': 'TJES',
  '09': 'TJGO',
  '10': 'TJMA',
  '11': 'TJMT',
  '12': 'TJMS',
  '13': 'TJMG',
  '14': 'TJPA',
  '15': 'TJPB',
  '16': 'TJPR',
  '17': 'TJPE',
  '18': 'TJPI',
  '19': 'TJRJ',
  '20': 'TJRN',
  '21': 'TJRS',
  '22': 'TJRO',
  '23': 'TJRR',
  '24': 'TJSC',
  '25': 'TJSE',
  '26': 'TJSP',
  '27': 'TJTO',
}

export function inferTribunalFromCnj(numeroCnj?: string | null): string | null {
  const digits = (numeroCnj ?? '').replace(/\D/g, '')
  if (digits.length !== 20) return null

  const ramo = digits[13]
  const tribunalCode = digits.slice(14, 16)

  if (ramo === '8') return TJ_BY_CODE[tribunalCode] ?? null
  if (ramo === '4' && ['01', '02', '03', '04', '05', '06'].includes(tribunalCode)) {
    return `TRF${Number(tribunalCode)}`
  }
  if (ramo === '6') return 'STJ'
  if (ramo === '7') return 'STM'

  return null
}
