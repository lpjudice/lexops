const STORAGE_KEY = 'gestor_jusbr_token'

function decodePayload(token: string): Record<string, unknown> | null {
  try {
    const [, payload] = token.split('.')
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4)
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

export function sanitizeJusbrToken(raw: string): string {
  return raw.trim().replace(/^Bearer\s+/i, '')
}

export function getJusbrTokenMeta(token: string): { exp: number | null; expired: boolean } {
  const payload = decodePayload(token)
  const exp = typeof payload?.exp === 'number' ? payload.exp : null
  const now = Math.floor(Date.now() / 1000)
  return { exp, expired: exp !== null ? exp <= now : false }
}

export function loadStoredJusbrToken(): string {
  if (typeof window === 'undefined') return ''
  const token = sanitizeJusbrToken(window.localStorage.getItem(STORAGE_KEY) ?? '')
  if (!token) return ''
  const meta = getJusbrTokenMeta(token)
  if (meta.expired) {
    window.localStorage.removeItem(STORAGE_KEY)
    return ''
  }
  return token
}

export function saveStoredJusbrToken(token: string): void {
  if (typeof window === 'undefined') return
  const sanitized = sanitizeJusbrToken(token)
  if (!sanitized) return
  window.localStorage.setItem(STORAGE_KEY, sanitized)
}

export function clearStoredJusbrToken(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(STORAGE_KEY)
}

export function formatTokenExpiry(token: string): string | null {
  const { exp } = getJusbrTokenMeta(token)
  if (!exp) return null
  return new Date(exp * 1000).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
