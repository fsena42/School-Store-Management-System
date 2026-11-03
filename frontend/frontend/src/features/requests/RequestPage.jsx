
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './RequestPage.css'

function RequestsPage({ onBack, stores = [] }) {
  const [items, setItems] = useState([])
  const [requests, setRequests] = useState([])
  const [storeId, setStoreId] = useState('')
  const [selectedItem, setSelectedItem] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [draftItems, setDraftItems] = useState([])
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')


  async function loadData() {
    setLoading(true)
    setError('')

    try {
        const [itemsData, requestsData] = await Promise.all([
        apiRequest('/requestable-items/'),
        apiRequest('/my-requests/'),
      ])

        setItems(itemsData.items || [])
        setRequests(requestsData.requests || [])
    } catch (err) {
        setError(err.message || 'Could not load request information.')
    } finally {
        setLoading(false)
    }
  }


  useEffect(() => {
    loadData()
  }, [])

  const availableItems = items.filter(
    (item) => String(item.store_id) === storeId
  )

  function addItem() {
    setError('')
    setMessage('')

    const item = availableItems.find(
      (entry) => String(entry.item_id) === selectedItem
    )

    const amount = Number(quantity)

    if (!item) {
      setError('Select an item from the selected store.')
      return
    }

    if (!Number.isInteger(amount) || amount < 1) {
      setError('Quantity must be a positive whole number.')
      return
    }

    const existing = draftItems.find(
      (entry) => entry.item_id === item.item_id
    )

    if (existing) {
      setDraftItems((current) =>
        current.map((entry) =>
          entry.item_id === item.item_id
            ? { ...entry, quantity: entry.quantity + amount }
            : entry
        )
      )
    } else {
      setDraftItems((current) => [
        ...current,
        {
          item_id: item.item_id,
          item_name: item.item_name,
          quantity: amount,
        },
      ])
    }

    setSelectedItem('')
    setQuantity('1')
  }

  function removeItem(itemId) {
    setDraftItems((current) =>
      current.filter((item) => item.item_id !== itemId)
    )
  }

  async function saveDraft(submitAfterSaving = false) {
    setError('')
    setMessage('')

    if (!storeId) {
      setError('Select a store first.')
      return
    }

    if (draftItems.length === 0) {
      setError('Add at least one item to your request.')
      return
    }

    setSaving(true)

    try {
      const payload = {
        store_id: Number(storeId),
        items: draftItems.map((item) => ({
          item_id: item.item_id,
          quantity: item.quantity,
        })),
      }

      let result

      if (editingId !== null) {
        result = await apiRequest(`/requests/${editingId}/draft/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
      } else {
        result = await apiRequest('/requests/drafts/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
      }

      const requestId = editingId ?? result.request_id

      if (submitAfterSaving) {
        await apiRequest(`/requests/${requestId}/submit/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })

        setMessage('Request submitted successfully.')
      } else {
        setMessage(editingId !== null
          ? 'Draft updated successfully.'
          : 'Draft saved successfully.')
      }

      setEditingId(null)
      setDraftItems([])
      setStoreId('')
      await loadData()
    } catch (err) {
      setError(err.message || 'Could not save the request.')
    } finally {
      setSaving(false)
    }
  }

  function startEditing(request) {
    if (request.status.toLowerCase() !== 'draft') {
      setError('Only drafts can be edited.')
      return
    }

    setEditingId(request.request_id)
    setStoreId(String(request.store_id))
    setDraftItems(
      request.items.map((item) => ({
        item_id: item.item_id,
        item_name: item.item_name,
        quantity: item.quantity_requested,
      }))
    )
    setError('')
    setMessage('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function deleteDraft(requestId) {
    if (!window.confirm('Delete this draft permanently?')) return

    setError('')
    setMessage('')

    try {
      await apiRequest(`/requests/${requestId}/delete-draft/`, {
        method: 'DELETE',
      })

      setMessage('Draft deleted successfully.')
      await loadData()
    } catch (err) {
      setError(err.message || 'Could not delete the draft.')
    }
  }

  async function submitExistingDraft(requestId) {
    if (!window.confirm('Submit this draft for approval?')) return

    setError('')
    setMessage('')

    try {
      await apiRequest(`/requests/${requestId}/submit/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })

      setMessage('Request submitted successfully.')
      await loadData()
    } catch (err) {
      setError(err.message || 'Could not submit the draft.')
    }
  }

  if (loading) {
    return <main className="requests-page">Loading requests...</main>
  }

  return (
    <main className="requests-page">
      <header className="requests-header">
        <div>
          <p className="requests-eyebrow">SCHOOL STORE MANAGEMENT SYSTEM</p>
          <h1>Store Requests</h1>
          <p>Create requests, save drafts, and track their progress.</p>
        </div>

        <button className="requests-secondary" onClick={onBack}>
          Back to dashboard
        </button>
      </header>

      {error && <p className="requests-error">{error}</p>}
      {message && <p className="requests-success">{message}</p>}

      <section className="requests-panel">
        <h2>{editingId !== null ? 'Edit request draft' : 'Create a request'}</h2>

        <label htmlFor="request-store">Store</label>
        <select
          id="request-store"
          value={storeId}
          onChange={(event) => {
            setStoreId(event.target.value)
            setSelectedItem('')
          }}
        >
          <option value="">Select a store</option>
          {stores.map((store) => (
            <option key={store.storeid} value={String(store.storeid)}>
              {store.storename}
            </option>
          ))}
        </select>

        <div className="requests-add-row">
          <div>
            <label htmlFor="request-item">Item</label>
            <select
              id="request-item"
              value={selectedItem}
              onChange={(event) => setSelectedItem(event.target.value)}
              disabled={!storeId}
            >
              <option value="">Select an item</option>
              {availableItems.map((item) => (
                <option key={item.item_id} value={String(item.item_id)}>
                  {item.item_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="request-quantity">Quantity requested</label>
            <input
              id="request-quantity"
              type="number"
              min="1"
              step="1"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </div>

          <button type="button" onClick={addItem} disabled={!storeId}>
            Add item
          </button>
        </div>

        <h3>Items in this request</h3>

        {draftItems.length === 0 ? (
          <p>No items added yet.</p>
        ) : (
          <div className="requests-table-wrap">
            <table className="requests-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Quantity</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {draftItems.map((item) => (
                  <tr key={item.item_id}>
                    <td>{item.item_name}</td>
                    <td>{item.quantity}</td>
                    <td>
                      <button
                        type="button"
                        className="requests-danger"
                        onClick={() => removeItem(item.item_id)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="requests-actions">
          <button
            onClick={() => saveDraft(false)}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save draft'}
          </button>

          <button
            onClick={() => saveDraft(true)}
            disabled={saving}
          >
            Save and submit
          </button>

          {editingId !== null && (
            <button
              className="requests-secondary"
              onClick={() => {
                setEditingId(null)
                setDraftItems([])
                setStoreId('')
                setError('')
                setMessage('')
              }}
            >
              Cancel editing
            </button>
          )}
        </div>
      </section>

      <section className="requests-panel">
        <h2>My requests</h2>

        {requests.length === 0 ? (
          <p>You have not created any requests yet.</p>
        ) : (
          <div className="requests-table-wrap">
            <table className="requests-table">
              <thead>
                <tr>
                  <th>Request ID</th>
                  <th>Date</th>
                  <th>Store</th>
                  <th>Items</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => {
                  const isDraft =
                    request.status.toLowerCase() === 'draft'

                  return (
                    <tr key={request.request_id}>
                      <td>{request.request_id}</td>
                      <td>{request.request_date}</td>
                      <td>{request.store_name}</td>
                      <td>
                        {request.items.map((item) => (
                          <div key={item.item_id}>
                            {item.item_name} × {item.quantity_requested}
                          </div>
                        ))}
                      </td>
                      <td>{request.status}</td>
                      <td>
                        {isDraft ? (
                          <div className="requests-row-actions">
                            <button onClick={() => startEditing(request)}>
                              Edit
                            </button>
                            <button
                              className="requests-danger"
                              onClick={() => deleteDraft(request.request_id)}
                            >
                              Delete
                            </button>
                            <button
                              onClick={() => submitExistingDraft(request.request_id)}
                            >
                              Submit
                            </button>
                          </div>
                        ) : (
                          <span>Read only</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}

export default RequestsPage
