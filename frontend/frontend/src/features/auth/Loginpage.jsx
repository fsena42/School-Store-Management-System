
import { useState } from 'react'
import { apiRequest, getCsrfToken } from '../../api/client'
import './LoginPage.css'

function LoginPage({ onLogin }) {
  const setupParams = new URLSearchParams(window.location.search)
  const [setupMode, setSetupMode] = useState(setupParams.get('setup') === '1')
  const [setupComplete, setSetupComplete] = useState(false)
  const [staffId, setStaffId] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleAccountSetup(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    if (password !== confirmPassword) {
      setError('The passwords do not match.')
      setLoading(false)
      return
    }

    try {
      const result = await apiRequest('/account/setup/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: setupParams.get('uid'),
          token: setupParams.get('token'),
          password,
        }),
      })
      setSetupComplete(true)
      setSetupMode(false)
      setPassword('')
      setConfirmPassword('')
      window.history.replaceState({}, '', window.location.pathname)
      setError('')
      setMessage(result.message)
    } catch (err) {
      setError(err.message || 'Could not set up your account.')
    } finally {
      setLoading(false)
    }
  }

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

        {setupMode ? (
          <form onSubmit={handleAccountSetup}>
            <label htmlFor="setupPassword">Choose a password</label>
            <input
              id="setupPassword"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <label htmlFor="confirmPassword">Confirm password</label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
            {error && <p className="login-error" role="alert">{error}</p>}
            <button type="submit" disabled={loading}>
              {loading ? 'Setting password...' : 'Set password'}
            </button>
          </form>
        ) : (
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
          {setupComplete && (
            <p className="login-success" role="status">{message}</p>
          )}

          <button type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        )}

        <p className="login-footer">
          Access is restricted to registered school staff.
        </p>
      </section>
    </main>
  )
}

export default LoginPage
