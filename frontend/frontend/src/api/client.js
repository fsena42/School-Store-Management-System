
const API_BASE = '/api'

export async function getCsrfToken() {
  const response = await fetch(`${API_BASE}/csrf/`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Could not initialize secure login.')
  }

  const data = await response.json()
  return data.csrfToken
}

export async function apiRequest(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()

  const headers = {
    ...options.headers,
  }

  // Django requires a CSRF token for unsafe HTTP methods.
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    headers['X-CSRFToken'] = await getCsrfToken()
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    credentials: 'include',
    headers,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(
      data.error || data.detail || 'The request failed.'
    )
  }

  return data
}
