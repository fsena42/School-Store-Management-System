
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './InventoryPage.css'
import EditItemForm from './EditItemForm'
import DeleteItemDialog from './DeleteItemDialog'

function InventoryPage({ onBack }) {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [selectedStore, setSelectedStore] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [canManageInventory, setCanManageInventory] = useState(false)
  const [editingItem, setEditingItem] = useState(null)
  const [deletingItem, setDeletingItem] = useState(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [savingDelete, setSavingDelete] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [actionError, setActionError] = useState('')

  useEffect(() => {
    let active = true

    async function loadInventory() {
      try {
        const [inventoryData, dashboardData] = await Promise.all([
          apiRequest('/inventory/'),
          apiRequest('/dashboard/'),
        ])

        if (active) {
          setItems(inventoryData.items)
          const position = dashboardData.staff.position
          setCanManageInventory(
            position === 'Principal' || position === 'Store Manager'
          )
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Could not load inventory.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadInventory()

    return () => {
      active = false
    }
  }, [])
  async function handleSaveEdit(formData) {
    if (!editingItem) return

    setSavingEdit(true)
    setActionError('')
    setActionMessage('')

    try {
      const result = await apiRequest(
        `/inventory/${editingItem.item_id}/edit/`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(formData),
        }
      )

      setItems(current =>
        current.map(item =>
          item.item_id === result.item.item_id
            ? { ...item, ...result.item }
            : item
        )
      )

      setEditingItem(null)
      setActionMessage(result.message)
    } catch (err) {
      setActionError(err.message || 'Could not update item.')
    } finally {
      setSavingEdit(false)
    }
  }
  async function handleConfirmDelete() {
    if (!deletingItem) return

    setSavingDelete(true)
    setActionError('')
    setActionMessage('')

    try {
      const result = await apiRequest(
        `/inventory/${deletingItem.item_id}/delete/`,
        {
          method: 'DELETE',
        }
      )

      setItems(current =>
        current.filter(item => item.item_id !== deletingItem.item_id)
      )

      setDeletingItem(null)
      setActionMessage(result.message)
    } catch (err) {
      setActionError(err.message || 'Could not delete item.')
    } finally {
      setSavingDelete(false)
    }
  }
  const stores = [...new Map(
    items.map((item) => [
      item.store_id,
      { id: item.store_id, name: item.store_name },
    ])
  ).values()]

  const filteredItems = items.filter((item) => {
    const matchesSearch =
      item.item_name.toLowerCase().includes(search.toLowerCase()) ||
      item.store_name.toLowerCase().includes(search.toLowerCase())

    const matchesStore =
      selectedStore === 'all' ||
      String(item.store_id) === selectedStore

    return matchesSearch && matchesStore
  })

  if (loading) {
    return <main className="inventory-page">Loading inventory...</main>
  }

  return (
    <main className="inventory-page">
      <header className="inventory-header">
        <div>
          <p className="inventory-eyebrow">STOCK MANAGEMENT</p>
          <h1>Inventory</h1>
          <p className="inventory-subtitle">
            View items, available quantities and reorder levels.
          </p>
        </div>

        {onBack && (
          <button className="inventory-secondary" onClick={onBack}>
            Back to dashboard
          </button>
        )}
      </header>

      {error && <p className="inventory-error">{error}</p>}

      {!error && (
        <>
          {canManageInventory && (
            <p className="inventory-delete-guidance" role="note">
              Items can be deleted only when their stock is zero and they
              have no request, purchase, or audit history.
            </p>
          )}

          <section className="inventory-summary">
            <div>
              <span>Total item records</span>
              <strong>{items.length}</strong>
            </div>
            <div>
              <span>Low-stock items</span>
              <strong>
                {items.filter(
                  (item) => item.quantity <= item.reorder_level
                ).length}
              </strong>
            </div>
          </section>

          <section className="inventory-controls">
            <input
              type="search"
              placeholder="Search item or store..."
              aria-label="Search inventory"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />

            <select
              aria-label="Filter by store"
              value={selectedStore}
              onChange={(event) => setSelectedStore(event.target.value)}
            >
              <option value="all">All stores</option>
              {stores.map((store) => (
                <option key={store.id} value={String(store.id)}>
                  {store.name}
                </option>
              ))}
            </select>
          </section>
          {actionMessage && (
            <p className="success-message">{actionMessage}</p>
          )}

          {actionError && (
            <p className="error-message">{actionError}</p>
          )}
          <div className="inventory-table-wrap">
            <table className="inventory-table">
              <thead>
                <tr>
                  <th>Item ID</th>
                  <th>Item name</th>
                  <th>Store</th>
                  <th>Quantity</th>
                  <th>Reorder level</th>
                  <th>Stock status</th>
                  {canManageInventory && <th>Actions</th>}
                </tr>
              </thead>

              <tbody>
                {filteredItems.map((item) => {
                  const lowStock = item.quantity <= item.reorder_level

                  return (
                    <tr key={item.item_id}>
                      <td>{item.item_id}</td>
                      <td>{item.item_name}</td>
                      <td>{item.store_name}</td>
                      <td>{item.quantity}</td>
                      <td>{item.reorder_level}</td>
                      <td>
                        <span className={
                          lowStock ? 'stock-status low' : 'stock-status normal'
                        }>
                          {lowStock ? 'Reorder needed' : 'In stock'}
                        </span>
                      </td>

                      {canManageInventory && (
                        <td>
                          <button
                            type="button"
                            className="inventory-secondary"
                            onClick={() => {
                              setEditingItem(item)
                              setActionMessage('')
                              setActionError('')
                            }}
                          >
                            Edit
                          </button>
                          {' '}
                          <button
                            type="button"
                            className="inventory-secondary inventory-delete"
                            disabled={Boolean(item.delete_block_reason)}
                            title={item.delete_block_reason || 'Delete item'}
                            aria-label={`Delete ${item.item_name}`}
                            onClick={() => {
                              setDeletingItem(item)
                              setActionMessage('')
                              setActionError('')
                            }}
                          >
                            Delete
                          </button>
                          {item.delete_block_reason && (
                            <span
                              className="inventory-delete-reason"
                              title={item.delete_block_reason}
                            >
                              {item.delete_block_reason}
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  )
                })}

                {filteredItems.length === 0 && (
                  <tr>
                    <td
                      colSpan={canManageInventory ? 7 : 6}
                      className="inventory-empty"
                    >
                      No matching inventory items found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
      {editingItem && (
        <EditItemForm
          item={editingItem}
          onSave={handleSaveEdit}
          onCancel={() => setEditingItem(null)}
          saving={savingEdit}
        />
      )}

      {deletingItem && (
        <DeleteItemDialog
          item={deletingItem}
          onConfirm={handleConfirmDelete}
          onCancel={() => setDeletingItem(null)}
          deleting={savingDelete}
        />
      )}      
    </main>
  )
}

export default InventoryPage
