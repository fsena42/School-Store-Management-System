import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './ApprovalsPage.css'

export default function IssuesPage({ onBack }) {
  const [requests, setRequests] = useState([])
  const [legacyReview, setLegacyReview] = useState([])
  const [legacyValues, setLegacyValues] = useState({})
  const [legacyReasons, setLegacyReasons] = useState({})
  const [quantities, setQuantities] = useState({})
  const [comments, setComments] = useState({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadIssues = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiRequest('/pending-issues/')
      setRequests(data.requests || [])
      setLegacyReview(data.legacy_review || [])
      setLegacyValues((previous) => {
        const next = { ...previous }
        for (const request of data.legacy_review || []) {
          next[request.request_id] ||= {}
          for (const item of request.items) {
            next[request.request_id][item.request_item_id] ||= {
              quantity_approved: '',
              quantity_previously_issued: '',
            }
          }
        }
        return next
      })
      setQuantities((previous) => {
        const next = {}
        for (const request of data.requests || []) {
          next[request.request_id] = {}
          for (const item of request.items) {
            next[request.request_id][item.request_item_id] =
              previous[request.request_id]?.[item.request_item_id] ??
              Math.min(item.quantity_remaining, item.quantity_in_stock)
          }
        }
        return next
      })
    } catch (err) {
      setError(err.message || 'Could not load approved items to issue.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadIssues()
  }, [loadIssues])

  async function submitIssue(request) {
    const items = request.items
      .map((item) => ({
        request_item_id: item.request_item_id,
        quantity: Number(quantities[request.request_id]?.[item.request_item_id] || 0),
      }))
      .filter((item) => item.quantity > 0)

    if (items.length === 0) {
      setError('Enter an in-stock quantity for at least one item.')
      return
    }

    async function reconcileLegacy(request) {
      const items = request.items.map((item) => {
        const values = legacyValues[request.request_id]?.[item.request_item_id] || {}
        return {
          request_item_id: item.request_item_id,
          approvedRaw: values.quantity_approved,
          issuedRaw: values.quantity_previously_issued,
          quantity_approved: Number(values.quantity_approved),
          quantity_previously_issued: Number(values.quantity_previously_issued),
        }
      })
      if (items.some((item) =>
        item.approvedRaw === '' ||
        item.issuedRaw === '' ||
        !Number.isInteger(item.quantity_approved) ||
        !Number.isInteger(item.quantity_previously_issued) ||
        item.quantity_approved < 0 ||
        item.quantity_previously_issued < 0 ||
        item.quantity_previously_issued > item.quantity_approved
      )) {
        setError('Enter verified whole-number quantities; previously issued cannot exceed approved.')
        return
      }
      const payloadItems = items.map(({ approvedRaw, issuedRaw, ...item }) => item)
      const reason = legacyReasons[request.request_id] || ''
      if (!reason.trim()) {
        setError('Describe how the historical quantities were verified.')
        return
      }
      setBusyId(request.request_id)
      setError('')
      setMessage('')
      try {
        const result = await apiRequest(`/requests/${request.request_id}/legacy-review/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: payloadItems, reason }),
        })
        setMessage(result.message)
        await loadIssues()
      } catch (err) {
        setError(err.message || 'Could not reconcile this legacy request.')
      } finally {
        setBusyId(null)
      }
    }

    setBusyId(request.request_id)
    setError('')
    setMessage('')
    try {
      const result = await apiRequest(`/requests/${request.request_id}/issue/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items,
          comments: comments[request.request_id] || '',
        }),
      })
      setMessage(result.message)
      await loadIssues()
    } catch (err) {
      setError(err.message || 'Could not issue these items.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <main className="dashboard-shell approvals-page">
      <header className="dashboard-header">
        <div>
          <p className="dashboard-eyebrow">SCHOOL STORE MANAGEMENT SYSTEM</p>
          <h1>Issue approved stock</h1>
          <p className="dashboard-subtitle">
            Stock is deducted only when the Store Manager records a physical issue.
          </p>
        </div>
        <button onClick={onBack}>← Back to dashboard</button>
      </header>

      {error && <p className="approvals-error" role="alert">{error}</p>}
      {message && <p className="approvals-message" role="status">{message}</p>}

      {legacyReview.length > 0 && (
        <section className="approval-card" aria-labelledby="legacy-requests-heading">
          <h2 id="legacy-requests-heading">Legacy requests need review</h2>
          <p>{legacyReview[0].message} Check the requester and records before confirming quantities.
            Historical issues are documented without changing current stock.
          </p>
          {legacyReview.map((request) => (
            <article key={request.request_id}>
              <h3>Request #{request.request_id} · {request.requester} · {request.store_name}</h3>
              <div className="approval-items">
                {request.items.map((item) => {
                  const values = legacyValues[request.request_id]?.[item.request_item_id] || {}
                  return (
                    <div className="approval-item" key={item.request_item_id}>
                      <div className="approval-item-details">
                        <strong>{item.item_name}</strong>
                        <span>Requested {item.quantity_requested} · old field recorded {item.legacy_quantity_recorded}</span>
                      </div>
                      <label>
                        Verified approved
                        <input
                          type="number"
                          min="0"
                          max={item.quantity_requested}
                          value={values.quantity_approved}
                          onChange={(event) => setLegacyValues((current) => ({
                            ...current,
                            [request.request_id]: {
                              ...current[request.request_id],
                              [item.request_item_id]: {
                                ...current[request.request_id]?.[item.request_item_id],
                                quantity_approved: event.target.value,
                              },
                            },
                          }))}
                        />
                      </label>
                      <label>
                        Verified previously issued
                        <input
                          type="number"
                          min="0"
                          max={values.quantity_approved || item.quantity_requested}
                          value={values.quantity_previously_issued}
                          onChange={(event) => setLegacyValues((current) => ({
                            ...current,
                            [request.request_id]: {
                              ...current[request.request_id],
                              [item.request_item_id]: {
                                ...current[request.request_id]?.[item.request_item_id],
                                quantity_previously_issued: event.target.value,
                              },
                            },
                          }))}
                        />
                      </label>
                    </div>
                  )
                })}
              </div>
              <label>
                Verification notes
                <textarea
                  rows={2}
                  maxLength={1000}
                  value={legacyReasons[request.request_id] || ''}
                  onChange={(event) => setLegacyReasons((current) => ({
                    ...current,
                    [request.request_id]: event.target.value,
                  }))}
                />
              </label>
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => reconcileLegacy(request)}
              >
                {busyId === request.request_id ? 'Saving review...' : 'Confirm verified history'}
              </button>
            </article>
          ))}
        </section>
      )}

      <section className="approvals-content">
        <div className="approvals-heading">
          <h2>Approved requests awaiting issue ({requests.length})</h2>
          <button onClick={loadIssues} disabled={loading || busyId !== null}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
        {loading ? (
          <p>Loading approved requests...</p>
        ) : requests.length === 0 ? (
          <p>There are no approved quantities awaiting issue.</p>
        ) : (
          <div className="approvals-list">
            {requests.map((request) => (
              <article className="approval-card" key={request.request_id}>
                <div className="approval-card-header">
                  <div>
                    <h3>Request #{request.request_id}</h3>
                    <p><strong>Requested by:</strong> {request.requester}</p>
                    <p><strong>Store:</strong> {request.store_name}</p>
                    <p><strong>Date:</strong> {request.request_date}</p>
                  </div>
                  <span className="approval-status">{request.status}</span>
                </div>
                <div className="approval-items">
                  {request.items.map((item) => {
                    const quantity = quantities[request.request_id]?.[item.request_item_id] ?? 0
                    return (
                      <div className="approval-item" key={item.request_item_id}>
                        <div className="approval-item-details">
                          <strong>{item.item_name}</strong>
                          <span>
                            Requested {item.quantity_requested} · Approved {item.quantity_approved}
                          </span>
                          <span>
                            Issued {item.quantity_issued} · Remaining {item.quantity_remaining}
                          </span>
                          <span>Currently in stock: {item.quantity_in_stock}</span>
                        </div>
                        <label className="approval-quantity-editor">
                          <span>Issue now</span>
                          <input
                            type="number"
                            min="0"
                            max={Math.min(item.quantity_remaining, item.quantity_in_stock)}
                            step="1"
                            value={quantity}
                            disabled={busyId !== null}
                            onChange={(event) => {
                              const parsed = event.target.value === '' ? '' : Number(event.target.value)
                              setQuantities((current) => ({
                                ...current,
                                [request.request_id]: {
                                  ...current[request.request_id],
                                  [item.request_item_id]: parsed,
                                },
                              }))
                            }}
                          />
                        </label>
                      </div>
                    )
                  })}
                </div>
                <label>
                  Issue notes
                  <input
                    value={comments[request.request_id] || ''}
                    maxLength={500}
                    onChange={(event) => setComments((current) => ({
                      ...current,
                      [request.request_id]: event.target.value,
                    }))}
                  />
                </label>
                <div className="approval-actions">
                  <button
                    onClick={() => submitIssue(request)}
                    disabled={busyId !== null}
                  >
                    {busyId === request.request_id ? 'Issuing...' : 'Record issue'}
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
