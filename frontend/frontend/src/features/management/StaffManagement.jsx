
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

const emptyForm = {
  surname: '',
  othernames: '',
  contact: '',
  email: '',
  department_id: '',
  position_id: '',
}

export default function StaffManagement() {
  const [data, setData] = useState({
    staff: [],
    departments: [],
    positions: [],
  })
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadStaff = useCallback(async () => {
    try {
      setError('')
      const result = await apiRequest('/management/staff/')
      setData(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStaff()
  }, [loadStaff])

  function update(field, value) {
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')

    try {
      const result = await apiRequest('/management/staff/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          department_id: Number(form.department_id),
          position_id: Number(form.position_id),
        }),
      })

      setMessage(
        `${result.message} Staff ID: ${result.staff_id}.`
      )
      setForm(emptyForm)
      await loadStaff()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function resendInvite(staffId) {
    setError('')
    setMessage('')
    try {
      const result = await apiRequest(`/management/staff/${staffId}/invite/`, {
        method: 'POST',
      })
      setMessage(result.message)
      await loadStaff()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="management-section">
      <h2>Staff management</h2>

      <form className="management-form" onSubmit={submit}>
        <label>
          Surname
          <input
            required
            maxLength={50}
            value={form.surname}
            onChange={(e) => update('surname', e.target.value)}
          />
        </label>

        <label>
          Other names
          <input
            required
            maxLength={100}
            value={form.othernames}
            onChange={(e) => update('othernames', e.target.value)}
          />
        </label>

        <label>
          Contact
          <input
            required
            maxLength={20}
            value={form.contact}
            onChange={(e) => update('contact', e.target.value)}
          />
        </label>

        <label>
          Email for account setup
          <input
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            value={form.email}
            onChange={(e) => update('email', e.target.value)}
          />
        </label>

        <label>
          Department
          <select
            required
            value={form.department_id}
            onChange={(e) => update('department_id', e.target.value)}
          >
            <option value="">Select department</option>
            {data.departments.map((department) => (
              <option
                key={department.departmentid}
                value={department.departmentid}
              >
                {department.departmentname}
              </option>
            ))}
          </select>
        </label>

        <label>
          Position
          <select
            required
            value={form.position_id}
            onChange={(e) => update('position_id', e.target.value)}
          >
            <option value="">Select position</option>
            {data.positions.map((position) => (
              <option
                key={position.positionid}
                value={position.positionid}
              >
                {position.positionname}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" disabled={saving}>
          {saving ? 'Saving...' : 'Register staff'}
        </button>
      </form>

      {error && <p className="management-error">{error}</p>}
      {message && <p className="management-success">{message}</p>}

      <h3>Registered staff</h3>

      {loading ? (
        <p>Loading staff...</p>
      ) : (
        <div className="management-table-wrap">
          <table className="management-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Department</th>
                <th>Position</th>
                <th>Contact</th>
                <th>Email / login</th>
                <th>Account action</th>
              </tr>
            </thead>
            <tbody>
              {data.staff.map((person) => (
                <tr key={person.staff_id}>
                  <td>{person.staff_id}</td>
                  <td>{person.surname} {person.othernames}</td>
                  <td>{person.department}</td>
                  <td>{person.position}</td>
                  <td>{person.contact}</td>
                  <td>
                    {person.email || '—'}
                    {person.email && (
                      <small> · {person.login_ready ? 'Ready' : 'Setup pending'}</small>
                    )}
                  </td>
                  <td>
                    {person.email && !person.login_ready && (
                      <button
                        type="button"
                        onClick={() => resendInvite(person.staff_id)}
                      >
                        Resend setup link
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {data.staff.length === 0 && (
                <tr>
                  <td colSpan="7">No staff records found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
