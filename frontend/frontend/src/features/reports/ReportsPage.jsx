
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import StaffReport from './StaffReport'
import InventoryReport from './InventoryReport'
import TransactionReport from './TransactionReport'
import './ReportsPage.css'

function ReportsPage({ onBack }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeReport, setActiveReport] = useState('overview')

  useEffect(() => {
    let active = true

    async function loadReports() {
      try {
        const data = await apiRequest('/reports/')
        if (active) setReport(data)
      } catch (err) {
        if (active) {
          setError(err.message || 'Failed to load reports.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadReports()

    return () => {
      active = false
    }
  }, [])

  if (loading) {
    return <main className="reports-page">Loading reports...</main>
  }

  if (error) {
    return (
      <main className="reports-page">
        <button onClick={onBack}>← Back to dashboard</button>
        <h1>Reports</h1>
        <p className="reports-error">{error}</p>
        <button onClick={() => window.location.reload()}>
          Try again
        </button>
      </main>
    )
  }

  const reportButtons = [
    { id: 'overview', label: 'Overview' },
    { id: 'staff', label: 'Staff' },
    { id: 'inventory', label: 'Inventory' },
    { id: 'transactions', label: 'Transactions' },
  ]

  return (
    <main className="reports-page">
      <header className="reports-header">
        <div>
          <p className="reports-eyebrow">SCHOOL STORE MANAGEMENT SYSTEM</p>
          <h1>Reports</h1>
          <p>Review staff, stock and purchasing activity.</p>
        </div>
        <button onClick={onBack}>← Back to dashboard</button>
      </header>

      <nav className="reports-tabs" aria-label="Report sections">
        {reportButtons.map((button) => (
          <button
            key={button.id}
            className={activeReport === button.id ? 'active' : ''}
            onClick={() => setActiveReport(button.id)}
          >
            {button.label}
          </button>
        ))}
      </nav>

      {activeReport === 'overview' && (
        <section className="reports-overview">
          <h2>Current overview</h2>

          <div className="reports-summary-grid">
            <article className="reports-summary-card">
              <span>Stores</span>
              <strong>{report?.stores?.length ?? 0}</strong>
            </article>

            <article className="reports-summary-card">
              <span>Inventory item records</span>
              <strong>
                {report?.stock_by_store?.reduce(
                  (total, store) => total + Number(store.item_count || 0),
                  0
                ) ?? 0}
              </strong>
            </article>

            <article className="reports-summary-card">
              <span>Purchase records</span>
              <strong>
                {report?.monthly_purchases?.reduce(
                  (total, month) => total + Number(month.purchase_count || 0),
                  0
                ) ?? 0}
              </strong>
            </article>

            <article className="reports-summary-card">
              <span>Goods received records</span>
              <strong>{report?.grn_count ?? 0}</strong>
            </article>
          </div>

          <p>
            Select a report above to examine the available information.
            Staff breakdowns, date-filtered movements and detailed
            transaction tables will be connected in the following steps.
          </p>
        </section>
      )}

      {activeReport === 'staff' && <StaffReport report={report} />}

      {activeReport === 'inventory' && (
        <InventoryReport report={report} />
      )}

      {activeReport === 'transactions' && (
        <TransactionReport report={report} />
      )}
    </main>
  )
}

export default ReportsPage
