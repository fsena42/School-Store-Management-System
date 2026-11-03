
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

function TransactionReport({ report }) {
  const monthly = report?.monthly_purchases ?? []
  const suppliers = report?.supplier_totals ?? []

  const money = (value) =>
    Number(value || 0).toLocaleString('en-UG', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })

  const totalPurchases = monthly.reduce(
    (sum, row) => sum + Number(row.purchase_count || 0),
    0
  )

  const totalSpent = monthly.reduce(
    (sum, row) => sum + Number(row.total_amount || 0),
    0
  )

  return (
    <section className="transaction-report">
      <h2>Transaction Report</h2>
      <p>Purchases recorded from suppliers.</p>

      <div className="reports-summary-grid">
        <article className="reports-summary-card">
          <span>Purchase records</span>
          <strong>{totalPurchases}</strong>
        </article>
        <article className="reports-summary-card">
          <span>Total recorded purchase value</span>
          <strong>UGX {money(totalSpent)}</strong>
        </article>
        <article className="reports-summary-card">
          <span>Suppliers with purchases</span>
          <strong>{suppliers.length}</strong>
        </article>
        <article className="reports-summary-card">
          <span>Goods received records</span>
          <strong>{report?.grn_count ?? 0}</strong>
        </article>
      </div>

      <section className="report-panel">
        <h3>Monthly purchases</h3>
        {monthly.length ? (
          <div className="report-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="total_amount" name="Purchase value (UGX)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p>No purchase records are available.</p>
        )}

        <div className="report-table-wrapper">
          <table className="report-table">
            <thead>
              <tr>
                <th>Month</th>
                <th>Purchase records</th>
                <th>Total value (UGX)</th>
              </tr>
            </thead>
            <tbody>
              {monthly.map((row) => (
                <tr key={row.month}>
                  <td>{row.month || 'Unknown'}</td>
                  <td>{row.purchase_count}</td>
                  <td>{money(row.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="report-panel">
        <h3>Purchases by supplier</h3>
        <div className="report-table-wrapper">
          <table className="report-table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Purchase records</th>
                <th>Total value (UGX)</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((supplier) => (
                <tr key={supplier.supplier_id}>
                  <td>{supplier.supplier_name}</td>
                  <td>{supplier.purchase_count}</td>
                  <td>{money(supplier.total_amount)}</td>
                </tr>
              ))}
              {!suppliers.length && (
                <tr>
                  <td colSpan="3">No supplier purchases found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <p>
        These are purchase summaries. Detailed invoice, GRN and item-level
        transaction records with date filtering require an additional
        backend response, which we will add next.
      </p>
    </section>
  )
}

export default TransactionReport
