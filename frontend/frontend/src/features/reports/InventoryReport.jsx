
import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../api/client'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'

function InventoryReport({ report }) {
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [storeId, setStoreId] = useState('')
  const [movements, setMovements] = useState(
    report?.stock_movements ?? []
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const stores = report?.stores ?? []
  const stockByStore = report?.stock_by_store ?? []

  useEffect(() => {
    setMovements(report?.stock_movements ?? [])
  }, [report])

  async function applyFilters(event) {
    event.preventDefault()

    if (fromDate && toDate && fromDate > toDate) {
      setError('The start date cannot be after the end date.')
      return
    }

    const params = new URLSearchParams()
    if (fromDate) params.set('from_date', fromDate)
    if (toDate) params.set('to_date', toDate)
    if (storeId) params.set('store_id', storeId)

    setLoading(true)
    setError('')

    try {
      const query = params.toString()
      const data = await apiRequest(
        `/reports/${query ? `?${query}` : ''}`
      )
      setMovements(data.stock_movements ?? [])
    } catch (err) {
      setError(err.message || 'Could not load stock movements.')
    } finally {
      setLoading(false)
    }
  }

  function clearFilters() {
    setFromDate('')
    setToDate('')
    setStoreId('')
    setError('')
    setMovements(report?.stock_movements ?? [])
  }

  const movementByDate = useMemo(() => {
    const daily = {}

    for (const movement of movements) {
      const day = movement.changed_at?.slice(0, 10)
      if (!day) continue

      if (!daily[day]) {
        daily[day] = { date: day, stockIn: 0, stockOut: 0 }
      }

      const change = Number(movement.quantity_change || 0)

      if (change > 0) daily[day].stockIn += change
      if (change < 0) daily[day].stockOut += Math.abs(change)
    }

    return Object.values(daily).sort((a, b) =>
      a.date.localeCompare(b.date)
    )
  }, [movements])

  const totalIn = movements.reduce(
    (sum, movement) =>
      sum + Math.max(0, Number(movement.quantity_change || 0)),
    0
  )

  const totalOut = movements.reduce(
    (sum, movement) =>
      sum + Math.abs(Math.min(0, Number(movement.quantity_change || 0))),
    0
  )

  return (
    <section className="inventory-report">
      <div className="report-section-heading">
        <div>
          <h2>Inventory Report</h2>
          <p>Current stock and recorded inventory changes.</p>
        </div>
      </div>

      <div className="reports-summary-grid">
        <article className="reports-summary-card">
          <span>Stores</span>
          <strong>{stores.length}</strong>
        </article>

        <article className="reports-summary-card">
          <span>Item records</span>
          <strong>
            {stockByStore.reduce(
              (sum, store) => sum + Number(store.item_count || 0),
              0
            )}
          </strong>
        </article>

        <article className="reports-summary-card">
          <span>Recorded quantity increases</span>
          <strong>{totalIn}</strong>
        </article>

        <article className="reports-summary-card">
          <span>Recorded quantity decreases</span>
          <strong>{totalOut}</strong>
        </article>
      </div>

      <section className="report-panel">
        <h3>Current stock by store</h3>

        <div className="report-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stockByStore}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="storeid__storename" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="total_quantity" name="Units in stock" />
              <Bar dataKey="item_count" name="Item records" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="report-table-wrapper">
          <table className="report-table">
            <thead>
              <tr>
                <th>Store</th>
                <th>Item records</th>
                <th>Total quantity</th>
                <th>Low-stock items</th>
              </tr>
            </thead>
            <tbody>
              {stockByStore.map((store) => (
                <tr key={store.storeid}>
                  <td>{store.storeid__storename}</td>
                  <td>{store.item_count}</td>
                  <td>{store.total_quantity}</td>
                  <td>{store.low_stock_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="report-panel">
        <h3>Filter recorded stock movements</h3>

        <form className="report-filters" onSubmit={applyFilters}>
          <label>
            From date
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
            />
          </label>

          <label>
            To date
            <input
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
            />
          </label>

          <label>
            Store
            <select
              value={storeId}
              onChange={(event) => setStoreId(event.target.value)}
            >
              <option value="">All stores</option>
              {stores.map((store) => (
                <option key={store.storeid} value={store.storeid}>
                  {store.storename}
                </option>
              ))}
            </select>
          </label>

          <div className="report-filter-actions">
            <button type="submit" disabled={loading}>
              {loading ? 'Loading...' : 'Apply filters'}
            </button>
            <button type="button" onClick={clearFilters}>
              Clear
            </button>
          </div>
        </form>

        {error && <p className="reports-error">{error}</p>}

        <p>
          Showing {movements.length} recorded quantity changes. Increases
          and decreases are calculated from the old and new quantities
          stored in the audit log.
        </p>

        <div className="report-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={movementByDate}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="stockIn"
                name="Quantity in"
                stroke="#16803c"
              />
              <Line
                type="monotone"
                dataKey="stockOut"
                name="Quantity out"
                stroke="#c0392b"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="report-table-wrapper">
          <table className="report-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Item</th>
                <th>Action</th>
                <th>Old quantity</th>
                <th>New quantity</th>
                <th>Change</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((movement) => (
                <tr key={movement.audit_id}>
                  <td>{movement.changed_at?.slice(0, 10)}</td>
                  <td>{movement.item_name}</td>
                  <td>{movement.action}</td>
                  <td>{movement.old_quantity}</td>
                  <td>{movement.new_quantity}</td>
                  <td>
                    {movement.quantity_change > 0 ? '+' : ''}
                    {movement.quantity_change}
                  </td>
                  <td>{movement.comments}</td>
                </tr>
              ))}

              {movements.length === 0 && (
                <tr>
                  <td colSpan="7">No recorded movements match these filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}

export default InventoryReport
