import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './ReceivingPage.css'

function localDate() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export default function PurchaseOrdersPage({ onBack }) {
  const [options, setOptions] = useState({ stores: [], suppliers: [], items: [] })
  const [orders, setOrders] = useState([])
  const [orderNumber, setOrderNumber] = useState('')
  const [storeId, setStoreId] = useState('')
  const [supplierId, setSupplierId] = useState('')
  const [orderDate, setOrderDate] = useState(localDate())
  const [expectedDate, setExpectedDate] = useState('')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [receiving, result] = await Promise.all([
        apiRequest('/receiving/options/'),
        apiRequest('/purchase-orders/'),
      ])
      setOptions(receiving)
      setOrders(result.purchase_orders || [])
    } catch (err) {
      setError(err.message || 'Could not load purchase order data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadInitialData() {
      try {
        const [receiving, result] = await Promise.all([
          apiRequest('/receiving/options/'),
          apiRequest('/purchase-orders/'),
        ])
        if (active) {
          setOptions(receiving)
          setOrders(result.purchase_orders || [])
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Could not load purchase order data.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadInitialData()
    return () => {
      active = false
    }
  }, [])

  const availableItems = options.items.filter((item) =>
    String(item.store_id) === storeId &&
    !lines.some((line) => String(line.item_id) === String(item.item_id))
  )

  function addLine() {
    if (!storeId || !availableItems.length) return
    const item = availableItems[0]
    setLines((current) => [...current, {
      item_id: String(item.item_id),
      quantity: '1',
      unit_cost: '',
    }])
  }

  function updateLine(index, field, value) {
    setLines((current) => current.map((line, i) =>
      i === index ? { ...line, [field]: value } : line
    ))
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (!lines.length) {
      setError('Add at least one item to the purchase order.')
      return
    }
    const items = lines.map((line) => ({
      item_id: Number(line.item_id),
      quantity: Number(line.quantity),
      unit_cost: line.unit_cost,
    }))
    if (items.some((line) =>
      !Number.isInteger(line.quantity) || line.quantity < 1 ||
      line.unit_cost === '' || !Number.isFinite(Number(line.unit_cost)) ||
      Number(line.unit_cost) < 0
    )) {
      setError('Enter a positive whole-number quantity and a valid unit cost for each line.')
      return
    }
    setSaving(true)
    try {
      const result = await apiRequest('/purchase-orders/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_number: orderNumber,
          store_id: Number(storeId),
          supplier_id: Number(supplierId),
          order_date: orderDate,
          expected_date: expectedDate || null,
          notes,
          items,
        }),
      })
      setMessage(result.message)
      setOrderNumber('')
      setStoreId('')
      setSupplierId('')
      setOrderDate(localDate())
      setExpectedDate('')
      setNotes('')
      setLines([])
      await loadData()
    } catch (err) {
      setError(err.message || 'Could not submit the purchase order.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="receiving-page">
      <header className="receiving-page-header">
        <div>
          <p className="receiving-eyebrow">PROCUREMENT</p>
          <h1>Purchase orders</h1>
          <p>Submit planned purchases for Principal or Deputy Principal approval.</p>
        </div>
        <button type="button" className="receiving-back-button" onClick={onBack}>
          ← Back to dashboard
        </button>
      </header>

      {error && <div className="receiving-message receiving-error" role="alert">{error}</div>}
      {message && <div className="receiving-message receiving-success" role="status">{message}</div>}

      <form onSubmit={submit}>
        <section className="receiving-panel">
          <h2>New purchase order</h2>
          <div className="receiving-form-grid">
            <label>
              Purchase order number
              <input required maxLength={30} value={orderNumber} onChange={(event) => setOrderNumber(event.target.value)} />
            </label>
            <label>
              Store
              <select required value={storeId} onChange={(event) => { setStoreId(event.target.value); setLines([]) }}>
                <option value="">Select store</option>
                {options.stores.map((store) => <option key={store.storeid} value={store.storeid}>{store.storename}</option>)}
              </select>
            </label>
            <label>
              Supplier
              <select required value={supplierId} onChange={(event) => setSupplierId(event.target.value)}>
                <option value="">Select supplier</option>
                {options.suppliers.map((supplier) => <option key={supplier.supplierid} value={supplier.supplierid}>{supplier.suppliername}</option>)}
              </select>
            </label>
            <label>
              Order date
              <input type="date" required value={orderDate} onChange={(event) => setOrderDate(event.target.value)} />
            </label>
            <label>
              Expected delivery
              <input type="date" min={orderDate} value={expectedDate} onChange={(event) => setExpectedDate(event.target.value)} />
            </label>
            <label className="receiving-full-width">
              Notes
              <textarea maxLength={1000} rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
          </div>
        </section>

        <section className="receiving-panel">
          <div className="receiving-section-heading">
            <div><h2>Ordered items</h2><p>Quantities and costs are reviewed before approval.</p></div>
            <button type="button" className="receiving-secondary-button" onClick={addLine} disabled={!storeId || !availableItems.length}>+ Add item</button>
          </div>
          {lines.map((line, index) => (
            <div className="receiving-form-grid" key={`${line.item_id}-${index}`}>
              <label>
                Item
                <select required value={line.item_id} onChange={(event) => updateLine(index, 'item_id', event.target.value)}>
                  <option value={line.item_id}>{options.items.find((item) => String(item.item_id) === line.item_id)?.item_name}</option>
                  {availableItems.map((item) => <option key={item.item_id} value={item.item_id}>{item.item_name}</option>)}
                </select>
              </label>
              <label>
                Quantity ordered
                <input type="number" min="1" step="1" required value={line.quantity} onChange={(event) => updateLine(index, 'quantity', event.target.value)} />
              </label>
              <label>
                Estimated unit cost
                <input type="number" min="0" step="0.01" required value={line.unit_cost} onChange={(event) => updateLine(index, 'unit_cost', event.target.value)} />
              </label>
              <button type="button" className="receiving-secondary-button" onClick={() => setLines((current) => current.filter((_, i) => i !== index))}>Remove</button>
            </div>
          ))}
          <button type="submit" disabled={saving || loading}>{saving ? 'Submitting...' : 'Submit for approval'}</button>
        </section>
      </form>

      <section className="receiving-panel">
        <h2>Purchase order history</h2>
        {loading ? <p>Loading orders...</p> : orders.length === 0 ? <p>No purchase orders yet.</p> : (
          <div className="receiving-table-wrap">
            <table className="receiving-table">
              <thead><tr><th>Order</th><th>Store</th><th>Supplier</th><th>Status</th><th>Items</th></tr></thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.purchase_order_id}>
                    <td>{order.order_number}</td><td>{order.store_name}</td><td>{order.supplier_name}</td><td>{order.status}</td>
                    <td>{order.lines.map((line) => `${line.item_name}: ${line.quantity_received}/${line.quantity_ordered}`).join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
