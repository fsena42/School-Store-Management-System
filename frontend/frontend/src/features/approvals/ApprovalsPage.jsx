
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './ApprovalsPage.css'

function ApprovalsPage({ onBack }) {
  const [requests, setRequests] = useState([])
  const [purchaseOrders, setPurchaseOrders] = useState([])
  const [requestHistory, setRequestHistory] = useState([])
  const [tab, setTab] = useState('requests')
  const [quantities, setQuantities] = useState({})
  const [reasons, setReasons] = useState({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadRequests = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiRequest('/pending-requests/')
      const pending = data.requests || []

      setRequests(pending)

      setQuantities((previous) => {
        const next = {}

        for (const req of pending) {
          next[req.request_id] = {}

          for (const item of req.items) {
            next[req.request_id][item.request_item_id] =
              previous[req.request_id]?.[item.request_item_id] ??
              item.quantity_requested
          }
        }

        return next
      })
    } catch (err) {
      setError(err.message || 'Could not load pending requests.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRequests()
  }, [loadRequests])

  const loadPurchaseOrders = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiRequest('/pending-purchase-orders/')
      setPurchaseOrders(data.purchase_orders || [])
    } catch (err) {
      setError(err.message || 'Could not load purchase orders.')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadRequestHistory = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiRequest('/request-issue-history/')
      setRequestHistory(data.requests || [])
    } catch (err) {
      setError(err.message || 'Could not load request issue progress.')
    } finally {
      setLoading(false)
    }
  }, [])

  async function decidePurchaseOrder(order, decision) {
    const key = `po-${order.purchase_order_id}`
    const reason = reasons[key] || ''
    if (decision === 'REJECTED' && !reason.trim()) {
      setError('Enter a reason before rejecting this purchase order.')
      return
    }
    setBusyId(order.purchase_order_id)
    setError('')
    setMessage('')
    try {
      const result = await apiRequest(
        `/purchase-orders/${order.purchase_order_id}/decision/`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision, reason }),
        }
      )
      setMessage(result.message)
      await loadPurchaseOrders()
    } catch (err) {
      setError(err.message || 'Could not decide this purchase order.')
    } finally {
      setBusyId(null)
    }
  }

  function changeQuantity(requestId, item, value) {
    setQuantities((previous) => ({
      ...previous,
      [requestId]: {
        ...previous[requestId],
        [item.request_item_id]: value,
      },
    }))
  }

  async function decideRequest(req, decision) {
    const action = decision === 'approve' ? 'approve' : 'reject'
    const reason = reasons[req.request_id] || ''

    if (action === 'reject' && !reason.trim()) {
      setError('Enter a reason before rejecting this request.')
      return
    }

    if (
      !window.confirm(
        `Are you sure you want to ${action} request #${req.request_id}?`
      )
    ) {
      return
    }

    setBusyId(req.request_id)
    setError('')
    setMessage('')

    try {
      let options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      }

      if (action === 'approve') {
        const items = req.items.map((item) => {
          const raw = quantities[req.request_id]?.[item.request_item_id]

          if (
            raw === '' ||
            raw === undefined ||
            !Number.isInteger(Number(raw)) ||
            Number(raw) < 0 ||
            Number(raw) > item.quantity_requested
          ) {
            throw new Error(
              `Enter a whole number from 0 to ${item.quantity_requested} for ${item.item_name}.`
            )
          }

          return {
            request_item_id: item.request_item_id,
            quantity_approved: Number(raw),
          }
        })

        options = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items, reason }),
        }
      }

      const result = await apiRequest(
        `/requests/${req.request_id}/${action}/`,
        options
      )

      setMessage(result.message || `Request ${action} successful.`)
      await loadRequests()
    } catch (err) {
      setError(err.message || `Could not ${action} this request.`)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <main className="dashboard-shell approvals-page">
      <header className="dashboard-header">
        <div>
          <p className="dashboard-eyebrow">
            SCHOOL STORE MANAGEMENT SYSTEM
          </p>
          <h1>Request approvals</h1>
          <p className="dashboard-subtitle">
            Review requested and available stock. Approval is separate from physical issue.
          </p>
        </div>

        <button onClick={onBack}>← Back to dashboard</button>
      </header>

      {error && (
        <p className="approvals-error" role="alert">
          {error}
        </p>
      )}

      {message && (
        <p className="approvals-message" role="status">
          {message}
        </p>
      )}

      <section className="approvals-content">
        <div className="approvals-heading">
          <div className="approval-actions">
            <button type="button" onClick={() => setTab('requests')} disabled={tab === 'requests'}>
              Requests
            </button>
            <button
              type="button"
              onClick={() => {
                setTab('purchase-orders')
                loadPurchaseOrders()
              }}
              disabled={tab === 'purchase-orders'}
            >
              Purchase orders
            </button>
            <button
              type="button"
              onClick={() => {
                setTab('history')
                loadRequestHistory()
              }}
              disabled={tab === 'history'}
            >
              Issue progress
            </button>
          </div>
        </div>
        {tab === 'requests' ? (
        <>
        <div className="approvals-heading">
          <h2>Pending requests ({requests.length})</h2>
          <button onClick={loadRequests} disabled={loading || busyId !== null}>
            ↻ {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {loading ? (
          <p>Loading pending requests...</p>
        ) : requests.length === 0 ? (
          <p>There are no pending requests to review.</p>
        ) : (
          <div className="approvals-list">
            {requests.map((req) => (
              <article className="approval-card" key={req.request_id}>
                <div className="approval-card-header">
                  <div>
                    <h3>Request #{req.request_id}</h3>
                    <p>
                      <strong>Requested by:</strong> {req.staff_name}
                    </p>
                    <p>
                      <strong>Staff ID:</strong> {req.staff_id}
                    </p>
                    <p>
                      <strong>Store:</strong> {req.store_name}
                    </p>
                    <p>
                      <strong>Date:</strong> {req.request_date}
                    </p>
                  </div>

                  <span className="approval-status">{req.status}</span>
                </div>

                <h4>Review requested items</h4>

                <div className="approval-items">
                  {req.items.map((item) => {
                    const value =
                      quantities[req.request_id]?.[item.request_item_id] ??
                      item.quantity_requested

                    return (
                      <div
                        className="approval-item"
                        key={item.request_item_id}
                      >
                        <div className="approval-item-details">
                          <strong>{item.item_name}</strong>
                          <span>
                            Requested: {item.quantity_requested}
                          </span>
                          <span>
                            Currently in stock: {item.quantity_in_stock}
                          </span>
                        </div>

                        <div className="approval-quantity-editor">
                          <button
                            type="button"
                            aria-label={`Decrease ${item.item_name} quantity`}
                            disabled={
                              busyId !== null ||
                              value === '' ||
                              Number(value) <= 0
                            }
                            onClick={() =>
                              changeQuantity(
                                req.request_id,
                                item,
                                Number(value) - 1
                              )
                            }
                          >
                            −
                          </button>

                          <label>
                            <span>Approve quantity</span>
                            <input
                              type="number"
                              min="0"
                              max={item.quantity_requested}
                              step="1"
                              value={value}
                              disabled={busyId !== null}
                              onChange={(event) =>
                                changeQuantity(
                                  req.request_id,
                                  item,
                                  event.target.value === ''
                                    ? ''
                                    : Number(event.target.value)
                                )
                              }
                            />
                          </label>

                          <button
                            type="button"
                            aria-label={`Increase ${item.item_name} quantity`}
                            disabled={
                              busyId !== null ||
                              value === '' ||
                              Number(value) >= item.quantity_requested
                            }
                            onClick={() =>
                              changeQuantity(
                                req.request_id,
                                item,
                                Number(value) + 1
                              )
                            }
                          >
                            +
                          </button>
                        </div>

                        {Number(value) < item.quantity_requested && (
                          <span className="approval-reduction">
                            Reduced by{' '}
                            {item.quantity_requested - Number(value)}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>

                <label className="approval-decision-reason">
                  {reasons[req.request_id]?.trim() ? 'Decision note / rejection reason' : 'Decision note (required to reject)'}
                  <textarea
                    value={reasons[req.request_id] || ''}
                    maxLength={1000}
                    rows={2}
                    onChange={(event) => setReasons((current) => ({
                      ...current,
                      [req.request_id]: event.target.value,
                    }))}
                  />
                </label>

                <div className="approval-actions">
                  <button
                    onClick={() => decideRequest(req, 'approve')}
                    disabled={busyId !== null}
                  >
                    {busyId === req.request_id
                      ? 'Processing...'
                      : 'Approve quantities'}
                  </button>

                  <button
                    className="reject-button"
                    onClick={() => decideRequest(req, 'reject')}
                    disabled={busyId !== null}
                  >
                    Reject request
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
        </>
        ) : tab === 'purchase-orders' ? (
          <>
            <div className="approvals-heading">
              <h2>Purchase orders awaiting approval ({purchaseOrders.length})</h2>
              <button onClick={loadPurchaseOrders} disabled={loading || busyId !== null}>
                {loading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            {loading ? <p>Loading purchase orders...</p> : purchaseOrders.length === 0 ? (
              <p>There are no purchase orders awaiting approval.</p>
            ) : (
              <div className="approvals-list">
                {purchaseOrders.map((order) => {
                  const key = `po-${order.purchase_order_id}`
                  return (
                    <article className="approval-card" key={order.purchase_order_id}>
                      <div className="approval-card-header">
                        <div>
                          <h3>{order.order_number}</h3>
                          <p><strong>Store:</strong> {order.store_name}</p>
                          <p><strong>Supplier:</strong> {order.supplier_name}</p>
                          <p><strong>Order date:</strong> {order.order_date}</p>
                          {order.expected_date && <p><strong>Expected delivery:</strong> {order.expected_date}</p>}
                          {order.notes && <p>{order.notes}</p>}
                        </div>
                        <span className="approval-status">{order.status}</span>
                      </div>
                      <ul>
                        {order.lines.map((line) => (
                          <li key={line.line_id}>
                            {line.item_name}: {line.quantity_ordered} × {line.unit_cost}
                          </li>
                        ))}
                      </ul>
                      <label className="approval-decision-reason">
                        Decision note / rejection reason
                        <textarea
                          rows={2}
                          maxLength={1000}
                          value={reasons[key] || ''}
                          onChange={(event) => setReasons((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))}
                        />
                      </label>
                      <div className="approval-actions">
                        <button disabled={busyId !== null} onClick={() => decidePurchaseOrder(order, 'APPROVED')}>
                          {busyId === order.purchase_order_id ? 'Processing...' : 'Approve order'}
                        </button>
                        <button className="reject-button" disabled={busyId !== null} onClick={() => decidePurchaseOrder(order, 'REJECTED')}>
                          Reject order
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </>
        ) : (
          <>
            <div className="approvals-heading">
              <h2>Request issue progress ({requestHistory.length})</h2>
              <button onClick={loadRequestHistory} disabled={loading || busyId !== null}>
                {loading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            {loading ? <p>Loading request progress...</p> : requestHistory.length === 0 ? (
              <p>No request history is available.</p>
            ) : (
              <div className="approvals-list">
                {requestHistory.map((request) => (
                  <article className="approval-card" key={request.request_id}>
                    <div className="approval-card-header">
                      <div>
                        <h3>Request #{request.request_id} · {request.requester}</h3>
                        <p>{request.store_name} · {request.request_date}</p>
                        {request.decision_reason && <p>Decision reason: {request.decision_reason}</p>}
                      </div>
                      <span className="approval-status">{request.status}</span>
                    </div>
                    {request.legacy_review_required && (
                      <p role="status">Legacy approval: verify physical issue history before further stock action.</p>
                    )}
                    <ul>
                      {request.items.map((item) => (
                        <li key={item.request_item_id}>
                          {item.item_name}: requested {item.quantity_requested},
                          {' '}approved {item.quantity_approved},
                          {' '}issued {item.quantity_issued},
                          {' '}remaining {item.quantity_remaining}
                          {item.legacy_review_required && ' (legacy quantity needs review)'}
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  )
}

export default ApprovalsPage
