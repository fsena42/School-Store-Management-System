
import { useState } from 'react'
import LoginPage from './features/auth/Loginpage'
import DashboardPage from './features/dashboard/DashboardPage'

function App() {
  const [staff, setStaff] = useState(null)

  if (!staff) {
    return <LoginPage onLogin={setStaff} />
  }

  return <DashboardPage onLogout={() => setStaff(null)} />
}

export default App
