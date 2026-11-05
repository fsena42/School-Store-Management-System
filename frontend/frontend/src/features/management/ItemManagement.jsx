
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

const emptyForm = {
  item_id: '',
  item_name: '',
  store_id: '',
  unit_id: '',
  reorder_level: '0',
}

export default function ItemManagement() {
  const [data, setData] = useState({ items: [], stores: [], units: [] })
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadItems = useCallback(async () => {
    try {
      setError('')
      setData(await apiRequest('/management/items/'))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadInitialItems() {
      try {
        const result = await apiRequest('/management/items/')
        if (active) {
          setData(result)
          setError('')
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }

    loadInitialItems()
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
      const result = await apiRequest('/management/items/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: Number(form.item_id),
          item_name: form.item_name,
          store_id: Number(form.store_id),
          unit_id: Number(form.unit_id),
          reorder_level: Number(form.reorder_level),
        }),
      })

      setMessage(result.message)
      setForm(emptyForm)
      await loadItems()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="management-section">
      <h2>Inventory item management</h2>

      <form className="management-form" onSubmit={submit}>
        <label>
          Item ID
          <input
            type="number"
            min="1"
            step="1"
            required
            value={form.item_id}
            onChange={(e) => update('item_id', e.target.value)}
          />
        </label>

        <label>
          Item name
          <input
            required
            maxLength={100}
            value={form.item_name}
            onChange={(e) => update('item_name', e.target.value)}
          />
        </label>

        <label>
          Store
          <select
            required
            value={form.store_id}
            onChange={(e) => update('store_id', e.target.value)}
          >
            <option value="">Select store</option>
            {data.stores.map((store) => (
              <option key={store.storeid} value={store.storeid}>
                {store.storename}
              </option>
            ))}
          </select>
        </label>

        <label>
          Unit of measurement
          <select
            required
            value={form.unit_id}
            onChange={(e) => update('unit_id', e.target.value)}
          >
            <option value="">Select unit</option>
            {data.units.map((unit) => (
              <option key={unit.unitid} value={unit.unitid}>
                {unit.unitname}
              </option>
            ))}
          </select>
        </label>

        <label>
          Reorder level
          <input
            type="number"
            min="0"
            step="1"
            required
            value={form.reorder_level}
            onChange={(e) => update('reorder_level', e.target.value)}
          />
        </label>

        <button type="submit" disabled={saving}>
          {saving ? 'Saving...' : 'Add item'}
        </button>
      </form>

      {error && <p className="management-error">{error}</p>}
      {message && <p className="management-success">{message}</p>}

      <h3>Inventory items</h3>

      {loading ? (
        <p>Loading items...</p>
      ) : (
        <div className="management-table-wrap">
          <table className="management-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Item</th>
                <th>Store</th>
                <th>Unit</th>
                <th>In stock</th>
                <th>Reorder level</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.item_id}>
                  <td>{item.item_id}</td>
                  <td>{item.item_name}</td>
                  <td>{item.store_name}</td>
                  <td>{item.unit_name}</td>
                  <td>{item.quantity}</td>
                  <td>{item.reorder_level}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan="6">No inventory items found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
