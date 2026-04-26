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

function extractJsonField(raw: string, field: string): string {
  const match = raw.match(new RegExp(`"${field}"\\s*:\\s*"([^"]+)"`, "i"))
  return match?.[1]?.trim() ?? ''
}

export function sanitizeJusbrToken(raw: string): string {
  return raw.trim().replace(/^Bearer\s+/i, '')
}

export function extractJusbrTokenFromText(raw: string): string {
  const text = raw.trim()
  if (!text) return ''

  const jsonToken = extractJsonField(text, 'access_token')
  if (jsonToken) return sanitizeJusbrToken(jsonToken)

  const patterns = [
    /authorization:\s*bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)/i,
    /["']authorization["']\s*:\s*["']Bearer\s+([^"']+)["']/i,
    /--header\s+['"]authorization:\s*Bearer\s+([^'"]+)['"]/i,
    /Bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)/i,
  ]

  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match?.[1]) return sanitizeJusbrToken(match[1])
  }

  const sanitized = sanitizeJusbrToken(text)
  if (sanitized.split('.').length === 3) return sanitized
  return ''
}

export function detectJusbrInputKind(raw: string): 'token_json' | 'process_response' | 'token' | 'curl' | 'headers' | 'unknown' {
  const text = raw.trim()
  if (!text) return 'unknown'
  if (extractJsonField(text, 'access_token')) return 'token_json'
  if (/"numeroProcesso"\s*:/i.test(text) || /"content"\s*:\s*\[/i.test(text)) return 'process_response'
  if (/^curl\s/i.test(text)) return 'curl'
  if (/authorization:/i.test(text) || /request headers/i.test(text)) return 'headers'
  if (sanitizeJusbrToken(text).split('.').length === 3) return 'token'
  return 'unknown'
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
  const sanitized = extractJusbrTokenFromText(token)
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
