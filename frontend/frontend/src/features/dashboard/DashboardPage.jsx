import { useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import InventoryPage from '../inventory/InventoryPage'
import RequestsPage from '../requests/RequestPage.jsx'
import ApprovalsPage from '../approvals/ApprovalsPage'
import ReceivingGoodsPage from '../receiving/ReceivingGoodsPage'
import ManagementPage from '../management/ManagementPage'
import ReportsPage from '../reports/ReportsPage'
import './DashboardPage.css'

function DashboardPage({ onLogout }) {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState('dashboard')

  useEffect(() => {
    let active = true

    async function loadDashboard() {
      try {
        const data = await apiRequest('/dashboard/')

        if (active) {
          setDashboard(data)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Could not load the dashboard.')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadDashboard()

    return () => {
      active = false
    }
  }, [])

  if (loading) {
    return (
      <main className="dashboard-shell">
        Loading dashboard...
      </main>
    )
  }

  if (error) {
    return (
      <main className="dashboard-shell">
        <section className="dashboard-error">
          <h1>Dashboard unavailable</h1>
          <p>{error}</p>
          <p>
            If your session has expired, sign in again. Otherwise,
            check that Django is running and the dashboard API is available.
          </p>
          <button onClick={onLogout}>
            Return to login
          </button>
        </section>
      </main>
    )
  }

  if (!dashboard || !dashboard.staff) {
    return (
      <main className="dashboard-shell">
        <section className="dashboard-error">
          <h1>Dashboard unavailable</h1>
          <p>The dashboard API returned incomplete staff information.</p>
          <button onClick={onLogout}>
            Return to login
          </button>
        </section>
      </main>
    )
  }

  const { staff, stores = [], can_approve } = dashboard

  const reportPositions = [
    'Principal',
    'Deputy Principal',
    'Store Manager',
    'Procurement Officer',
  ]

  const managementPositions = [
    'Principal',
    'Store Manager',
    'Procurement Officer',
  ]

  const canViewInventory = reportPositions.includes(staff.position)
  const canViewReports = reportPositions.includes(staff.position)
  const canManage = managementPositions.includes(staff.position)

  // Navigation
  if (currentPage === 'inventory' && canViewInventory) {
    return (
      <InventoryPage
        onBack={() => setCurrentPage('dashboard')}
      />
    )
  }

  if (currentPage === 'requests') {
    return (
      <RequestsPage
        onBack={() => setCurrentPage('dashboard')}
        stores={stores}
      />
    )
  }

  if (currentPage === 'approvals' && can_approve) {
    return (
      <ApprovalsPage
        onBack={() => setCurrentPage('dashboard')}
      />
    )
  }

  if (
    currentPage === 'receiving' &&
    staff.position === 'Store Manager'
  ) {
    return (
      <ReceivingGoodsPage
        onBack={() => setCurrentPage('dashboard')}
      />
    )
  }

  if (currentPage === 'reports' && canViewReports) {
    return (
      <ReportsPage
        onBack={() => setCurrentPage('dashboard')}
      />
    )
  }


  if (currentPage === 'management' && canManage) {
    return (
      <ManagementPage
        onBack={() => setCurrentPage('dashboard')}
      />
    )
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="dashboard-eyebrow">
            SCHOOL STORE MANAGEMENT SYSTEM
          </p>
          <h1>Dashboard</h1>
          <p className="dashboard-subtitle">
            Welcome, {staff.name}
          </p>
        </div>

        <button
          className="dashboard-logout"
          onClick={onLogout}
        >
          Return to login
        </button>
      </header>

      <section className="staff-summary">
        <div>
          <span>Staff ID</span>
          <strong>{staff.staff_id}</strong>
        </div>

        <div>
          <span>Position</span>
          <strong>{staff.position}</strong>
        </div>
      </section>

      <section className="dashboard-section">
        <h2>Your workspace</h2>
        <p className="section-description">
          Available functions are based on your assigned role.
        </p>

        <div className="dashboard-grid">
          {stores.length > 0 && (
            <article className="dashboard-card">
              <div className="card-icon">▦</div>
              <h3>Store requests</h3>
              <p>
                Request goods from the stores permitted for your position.
              </p>

              <ul>
                {stores.map((store) => (
                  <li key={store.storeid}>
                    {store.storename}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => setCurrentPage('requests')}
              >
                Make a request
              </button>
            </article>
          )}

          {can_approve && (
            <article className="dashboard-card">
              <div className="card-icon">✓</div>
              <h3>Request approvals</h3>
              <p>
                Review submitted requests and make approval decisions.
              </p>

              <button
                onClick={() => setCurrentPage('approvals')}
              >
                View approvals
              </button>
            </article>
          )}

          {canViewReports && (
            <article className="dashboard-card">
              <div className="card-icon">▤</div>
              <h3>Reports</h3>
              <p>
                Access the inventory report and transaction report.
              </p>

              <button
                onClick={() => setCurrentPage('reports')}
              >
                View reports
              </button>
            </article>
          )}

          {canManage && (
            <article className="dashboard-card">
              <div className="card-icon">⚙</div>
              <h3>Management</h3>
              <p>
                Manage inventory items, suppliers and units of measurement.
              </p>

              <button
                onClick={() => setCurrentPage('management')}
              >
                Manage inventory
              </button>
            </article>
          )}

          {staff.position === 'Store Manager' && (
            <article className="dashboard-card">
              <div className="card-icon">📦</div>
              <h3>Goods receiving</h3>
              <p>
                Record supplier invoices, GRNs and received goods.
              </p>

              <button
                onClick={() => setCurrentPage('receiving')}
              >
                Receive goods
              </button>
            </article>
          )}

          {canViewInventory && (
            <article className="dashboard-card">
              <div className="card-icon">▥</div>
              <h3>Inventory</h3>
              <p>
                View inventory information available to your role.
              </p>

              <button
                onClick={() => setCurrentPage('inventory')}
              >
                View inventory
              </button>
            </article>
          )}
        </div>
      </section>
    </main>
  )
}

export default DashboardPage