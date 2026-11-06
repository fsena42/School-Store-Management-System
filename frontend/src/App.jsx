
import { useEffect, useState } from 'react'
import LoginPage from './features/auth/Loginpage'
import DashboardPage from './features/dashboard/DashboardPage'
import { apiRequest } from './api/client'

function App() {
  const [staff, setStaff] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [logoutError, setLogoutError] = useState('')

  useEffect(() => {
    let active = true
    apiRequest('/session/')
      .then((session) => {
        if (active && session.authenticated) {
          setStaff({
            staff_id: session.staff_id,
            name: session.name,
            position: session.position,
          })
        }
      })
      .catch(() => {
        if (active) setStaff(null)
      })
      .finally(() => {
        if (active) setCheckingSession(false)
      })
    return () => {
      active = false
    }
  }, [])

  async function logout() {
    try {
      await apiRequest('/logout/', { method: 'POST' })
      setStaff(null)
      setLogoutError('')
    } catch (err) {
      setLogoutError(err.message || 'Could not sign out. Please try again.')
    }
  }

  if (checkingSession) {
    return <main className="dashboard-shell">Checking your session...</main>
  }
  if (!staff) {
    return <LoginPage onLogin={setStaff} />
  }

  return <DashboardPage onLogout={logout} logoutError={logoutError} />
}

export default App
