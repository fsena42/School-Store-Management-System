
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

const emptyForm = {
  supplier_id: '',
  supplier_name: '',
  contact: '',
  email: '',
  address: '',
}

export default function SupplierManagement() {
  const [suppliers, setSuppliers] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadSuppliers = useCallback(async () => {
    try {
      setError('')
      const result = await apiRequest('/management/suppliers/')
      setSuppliers(result.suppliers)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadInitialSuppliers() {
      try {
        const result = await apiRequest('/management/suppliers/')
        if (active) {
          setSuppliers(result.suppliers)
          setError('')
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }

    loadInitialSuppliers()
    return () => {
      active = false
    }
  }, [])

  function update(field, value) {
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')

    try {
      const result = await apiRequest('/management/suppliers/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supplier_id: Number(form.supplier_id),
          supplier_name: form.supplier_name,
          contact: form.contact,
          email: form.email,
          address: form.address,
        }),
      })

      setMessage(result.message)
      setForm(emptyForm)
      await loadSuppliers()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="management-section">
      <h2>Supplier management</h2>

      <form className="management-form" onSubmit={submit}>
        <label>
          Supplier ID
          <input
            type="number"
            min="1"
            step="1"
            required
            value={form.supplier_id}
            onChange={(e) => update('supplier_id', e.target.value)}
          />
        </label>

        <label>
          Supplier name
          <input
            required
            maxLength={100}
            value={form.supplier_name}
            onChange={(e) => update('supplier_name', e.target.value)}
          />
        </label>

        <label>
          Contact number
          <input
            required
            maxLength={20}
            value={form.contact}
            onChange={(e) => update('contact', e.target.value)}
          />
        </label>

        <label>
          Email (optional)
          <input
            type="email"
            maxLength={100}
            value={form.email}
            onChange={(e) => update('email', e.target.value)}
          />
        </label>

        <label>
          Address
          <input
            required
            maxLength={100}
            value={form.address}
            onChange={(e) => update('address', e.target.value)}
          />
        </label>

        <button type="submit" disabled={saving}>
          {saving ? 'Saving...' : 'Add supplier'}
        </button>
      </form>

      {error && <p className="management-error">{error}</p>}
      {message && <p className="management-success">{message}</p>}

      <h3>Registered suppliers</h3>

      {loading ? (
        <p>Loading suppliers...</p>
      ) : (
        <div className="management-table-wrap">
          <table className="management-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Supplier</th>
                <th>Contact</th>
                <th>Email</th>
                <th>Address</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((supplier) => (
                <tr key={supplier.supplier_id}>
                  <td>{supplier.supplier_id}</td>
                  <td>{supplier.supplier_name}</td>
                  <td>{supplier.contact}</td>
                  <td>{supplier.email || '—'}</td>
                  <td>{supplier.address}</td>
                </tr>
              ))}
              {suppliers.length === 0 && (
                <tr>
                  <td colSpan="5">No suppliers found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
