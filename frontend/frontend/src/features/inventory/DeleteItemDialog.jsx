
function DeleteItemDialog({ item, onConfirm, onCancel, deleting }) {
  if (!item) return null

  return (
    <div className="inventory-modal-overlay">
      <div className="inventory-modal">
        <h2>Delete item</h2>

        <p>
          Are you sure you want to delete <strong>{item.item_name}</strong>?
        </p>

        <p>
          This action cannot be undone.
        </p>

        <div className="inventory-modal-actions">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Confirm delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default DeleteItemDialog
