
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './ApprovalsPage.css'

function ApprovalsPage({ onBack }) {
  const [requests, setRequests] = useState([])
  const [quantities, setQuantities] = useState({})
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
      let options = { method: 'POST' }

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
          body: JSON.stringify({ items }),
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
            Review requests and adjust quantities before approving.
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
      </section>
    </main>
  )
}

export default ApprovalsPage
