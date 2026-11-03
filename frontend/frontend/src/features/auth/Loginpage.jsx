
import { useState } from 'react'
import { apiRequest, getCsrfToken } from '../../api/client'
import './LoginPage.css'

function LoginPage({ onLogin }) {
  const [staffId, setStaffId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLogin(event) {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const csrfToken = await getCsrfToken()

      const data = await apiRequest('/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          staff_id: staffId.trim(),
          password,
        }),
      })

      onLogin(data.staff)
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="login-brand">SS</div>

        <p className="login-eyebrow">SCHOOL STORE MANAGEMENT SYSTEM</p>
        <h1>Staff login</h1>
        <p className="login-subtitle">
          Sign in with your staff credentials to continue.
        </p>

        <form onSubmit={handleLogin}>
          <label htmlFor="staffId">Staff ID</label>
          <input
            id="staffId"
            type="text"
            inputMode="numeric"
            autoComplete="username"
            placeholder="Enter your staff ID"
            value={staffId}
            onChange={(event) => setStaffId(event.target.value)}
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="login-footer">
          Access is restricted to registered school staff.
        </p>
      </section>
    </main>
  )
}

export default LoginPage
