
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

function StaffReport({ report }) {
  const departments = report?.staff_by_department ?? []
  const positions = report?.staff_by_position ?? []

  const totalByDepartment = departments.reduce(
    (sum, department) => sum + Number(department.staff_count || 0),
    0
  )

  return (
    <section className="staff-report">
      <div className="report-section-heading">
        <div>
          <h2>Staff Report</h2>
          <p>Staff distribution across departments and positions.</p>
        </div>
      </div>

      <div className="reports-summary-grid">
        <article className="reports-summary-card">
          <span>Total staff</span>
          <strong>{report?.staff_total ?? 0}</strong>
        </article>

        <article className="reports-summary-card">
          <span>Departments</span>
          <strong>{departments.length}</strong>
        </article>

        <article className="reports-summary-card">
          <span>Positions</span>
          <strong>{positions.length}</strong>
        </article>
      </div>

      <section className="report-panel">
        <h3>Staff by department</h3>

        {departments.length === 0 ? (
          <p>No department records found.</p>
        ) : (
          <>
            <div className="report-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={departments}
                  margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="departmentname" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="staff_count" name="Staff" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="report-table-wrapper">
              <table className="report-table">
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Staff count</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((department) => (
                    <tr key={department.departmentid}>
                      <td>{department.departmentname}</td>
                      <td>{department.staff_count}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th>Total across departments</th>
                    <th>{totalByDepartment}</th>
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="report-panel">
        <h3>Staff by position</h3>

        {positions.length === 0 ? (
          <p>No position records found.</p>
        ) : (
          <>
            <div className="report-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={positions}
                  margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="positionname" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="staff_count" name="Staff" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="report-table-wrapper">
              <table className="report-table">
                <thead>
                  <tr>
                    <th>Position</th>
                    <th>Staff count</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.positionid}>
                      <td>{position.positionname}</td>
                      <td>{position.staff_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </section>
  )
}

export default StaffReport
