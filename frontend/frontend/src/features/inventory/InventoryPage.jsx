
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import './InventoryPage.css'

function InventoryPage({ onBack }) {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [selectedStore, setSelectedStore] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [canManageInventory, setCanManageInventory] = useState(false)

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
                              alert(
                                `Edit functionality for ${item.item_name} will be connected next.`
                              )
                            }}
                          >
                            Edit
                          </button>
                          {' '}
                          <button
                            type="button"
                            className="inventory-secondary"
                            onClick={() => {
                              alert(
                                `Delete functionality for ${item.item_name} will be connected next.`
                              )
                            }}
                          >
                            Delete
                          </button>
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
    </main>
  )
}

export default InventoryPage
