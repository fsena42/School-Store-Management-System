import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../api/client'
import ReceivingHeaderPage from './ReceivingHeaderPage'
import './ReceivingPage.css'

function today() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function emptyForm() {
  return {
    store_id: '',
    supplier_id: '',
    invoice_number: '',
    invoice_date: today(),
    purchase_date: today(),
    grn_number: '',
    grn_date: today(),
    remarks: '',
  }
}

export default function ReceivingGoodsPage({ onBack }) {
  const [options, setOptions] = useState({
    stores: [],
    suppliers: [],
    items: [],
  })
  const [form, setForm] = useState(emptyForm)
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true

    async function loadOptions() {
      try {
        const data = await apiRequest('/receiving/options/')
        if (active) setOptions(data)
      } catch (err) {
        if (active) setError(err.message || 'Could not load receiving data.')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadOptions()
    return () => {
      active = false
    }
  }, [])

  const availableItems = useMemo(() => {
    return options.items.filter(
      (item) =>
        String(item.store_id) === String(form.store_id) &&
        !lines.some((line) => String(line.item_id) === String(item.item_id)),
    )
  }, [options.items, form.store_id, lines])

  const total = lines.reduce(
    (sum, line) => sum + Number(line.quantity || 0) * Number(line.unit_cost || 0),
    0,
  )

  function handleHeaderChange(event) {
    const { name, value } = event.target

    setForm((previous) => ({ ...previous, [name]: value }))
    setError('')
    setSuccess('')

    if (name === 'store_id') {
      setLines([])
    }
  }

  function addLine() {
    if (!form.store_id) {
      setError('Select a store before adding items.')
      return
    }

    if (availableItems.length === 0) {
      setError('There are no more items available for this store.')
      return
    }

    setLines((previous) => [
      ...previous,
      {
        item_id: String(availableItems[0].item_id),
        quantity: '1',
        unit_cost: '',
      },
    ])
    setError('')
    setSuccess('')
  }

  function updateLine(index, field, value) {
    setLines((previous) =>
      previous.map((line, lineIndex) =>
        lineIndex === index ? { ...line, [field]: value } : line,
      ),
    )
    setError('')
    setSuccess('')
  }

  function removeLine(index) {
    setLines((previous) => previous.filter((_, i) => i !== index))
    setError('')
    setSuccess('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccess('')

    if (lines.length === 0) {
      setError('Add at least one item to the delivery.')
      return
    }

    const payloadItems = lines.map((line) => ({
      item_id: Number(line.item_id),
      quantity: Number(line.quantity),
      unit_cost: line.unit_cost,
    }))

    if (
      payloadItems.some(
        (line) =>
          !Number.isInteger(line.quantity) ||
          line.quantity <= 0 ||
          line.unit_cost === '' ||
          !Number.isFinite(Number(line.unit_cost)) ||
          Number(line.unit_cost) < 0,
      )
    ) {
      setError('Enter a positive whole-number quantity and a valid unit cost for every item.')
      return
    }

    setSaving(true)

    try {
      const result = await apiRequest('/receiving/receive/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          store_id: Number(form.store_id),
          supplier_id: Number(form.supplier_id),
          items: payloadItems,
        }),
      })

      setSuccess(
        `${result.message} GRN: ${result.grn_number}. Total: ${Number(
          result.total_amount,
        ).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}.`,
      )
      setForm(emptyForm())
      setLines([])
    } catch (err) {
      setError(err.message || 'Goods could not be recorded.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <main className="receiving-page">
        <p>Loading receiving information...</p>
      </main>
    )
  }

  return (
    <main className="receiving-page">
      <header className="receiving-page-header">
        <div>
          <p className="receiving-eyebrow">STORE MANAGEMENT</p>
          <h1>Goods receiving</h1>
          <p>Record supplier invoices, purchased items and goods received notes.</p>
        </div>

        <button
          type="button"
          className="receiving-back-button"
          onClick={onBack}
        >
          ← Back to dashboard
        </button>
      </header>

      {error && (
        <div className="receiving-message receiving-error" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="receiving-message receiving-success" role="status">
          {success}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <ReceivingHeaderPage
          form={form}
          onChange={handleHeaderChange}
          stores={options.stores}
          suppliers={options.suppliers}
        />

        <section className="receiving-panel">
          <div className="receiving-section-heading">
            <div>
              <h2>Items received</h2>
              <p>Add each item and enter the delivered quantity and unit cost.</p>
            </div>

            <button
              type="button"
              className="receiving-secondary-button"
              onClick={addLine}
              disabled={!form.store_id || availableItems.length === 0}
            >
              + Add item
            </button>
          </div>

          {lines.length === 0 ? (
            <div className="receiving-empty">
              No items added yet. Select a store, then click <strong>Add item</strong>.
            </div>
          ) : (
            <div className="receiving-table-wrap">
              <table className="receiving-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Quantity received</th>
                    <th>Unit cost</th>
                    <th>Subtotal</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>
                  {lines.map((line, index) => {
                    const selectedItem = options.items.find(
                      (item) => String(item.item_id) === String(line.item_id),
                    )
                    const subtotal =
                      Number(line.quantity || 0) * Number(line.unit_cost || 0)

                    return (
                      <tr key={`${line.item_id}-${index}`}>
                        <td>
                          <select
                            value={line.item_id}
                            onChange={(event) =>
                              updateLine(index, 'item_id', event.target.value)
                            }
                            aria-label={`Item ${index + 1}`}
                            required
                          >
                            {selectedItem && (
                              <option value={selectedItem.item_id}>
                                {selectedItem.item_name}
                              </option>
                            )}
                            {availableItems.map((item) => (
                              <option key={item.item_id} value={item.item_id}>
                                {item.item_name}
                              </option>
                            ))}
                          </select>
                          {selectedItem && (
                            <small className="receiving-stock-hint">
                              Current stock: {selectedItem.quantity_in_stock}
                            </small>
                          )}
                        </td>

                        <td>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={line.quantity}
                            onChange={(event) =>
                              updateLine(index, 'quantity', event.target.value)
                            }
                            aria-label={`Quantity for item ${index + 1}`}
                            required
                          />
                        </td>

                        <td>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={line.unit_cost}
                            onChange={(event) =>
                              updateLine(index, 'unit_cost', event.target.value)
                            }
                            aria-label={`Unit cost for item ${index + 1}`}
                            required
                          />
                        </td>

                        <td className="receiving-money">
                          {subtotal.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </td>

                        <td>
                          <button
                            type="button"
                            className="receiving-remove-button"
                            onClick={() => removeLine(index)}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="receiving-total">
            <span>Purchase total</span>
            <strong>
              {total.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </strong>
          </div>
        </section>

        <div className="receiving-submit-row">
          <button
            type="button"
            className="receiving-back-button"
            onClick={onBack}
            disabled={saving}
          >
            Cancel
          </button>

          <button
            type="submit"
            className="receiving-submit-button"
            disabled={saving}
          >
            {saving ? 'Recording delivery...' : 'Record goods received'}
          </button>
        </div>

        <p className="receiving-warning">
          Submitting records the purchase and GRN and increases stock. Confirm
          the quantities and document numbers before submitting. This screen
          records full delivery quantities, not partial deliveries.
        </p>
      </form>
    </main>
  )
}