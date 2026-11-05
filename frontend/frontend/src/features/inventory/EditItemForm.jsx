
import { useEffect, useState } from 'react'

function EditItemForm({ item, onSave, onCancel, saving }) {
  const [itemName, setItemName] = useState('')
  const [quantity, setQuantity] = useState('')
  const [reorderLevel, setReorderLevel] = useState('')
  const [comments, setComments] = useState('')

  useEffect(() => {
    if (item) {
      setItemName(item.item_name || '')
      setQuantity(String(item.quantity ?? ''))
      setReorderLevel(String(item.reorder_level ?? ''))
      setComments('')
    }
  }, [item])

  function handleSubmit(event) {
    event.preventDefault()

    if (
      !itemName.trim() ||
      quantity === '' ||
      reorderLevel === '' ||
      !comments.trim() ||
      !Number.isInteger(Number(quantity)) ||
      !Number.isInteger(Number(reorderLevel)) ||
      Number(quantity) < 0 ||
      Number(reorderLevel) < 0
    ) {
      return
    }

    onSave({
      item_name: itemName.trim(),
      quantity: Number(quantity),
      reorder_level: Number(reorderLevel),
      comments: comments.trim(),
    })
  }

  return (
    <div className="inventory-modal-overlay">
      <form className="inventory-modal" onSubmit={handleSubmit}>
        <h2>Edit inventory item</h2>

        <label>
          Item name
          <input
            type="text"
            value={itemName}
            onChange={(e) => setItemName(e.target.value)}
            required
          />
        </label>

        <label>
          Quantity
          <input
            type="number"
            min="0"
            step="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
        </label>

        <label>
          Reorder level
          <input
            type="number"
            min="0"
            step="1"
            value={reorderLevel}
            onChange={(e) => setReorderLevel(e.target.value)}
            required
          />
        </label>

        <label>
          Reason for change
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            placeholder="Explain why this item is being edited..."
            required
          />
        </label>

        <div className="inventory-modal-actions">
          <button type="button" onClick={onCancel} disabled={saving}>
            Cancel
          </button>

          <button type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default EditItemForm
