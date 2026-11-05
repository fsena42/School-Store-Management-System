export default function ReceivingHeaderPage({
  form,
  onChange,
  stores,
  suppliers,
  purchaseOrders,
  selectedOrder,
  onOrderChange,
}) {
  return (
    <section className="receiving-panel">
      <h2>Invoice & delivery details</h2>

      <div className="receiving-form-grid">
        <label>
          Approved purchase order
          <select
            name="purchase_order_id"
            value={form.purchase_order_id}
            onChange={onOrderChange}
            required
          >
            <option value="">Select an approved order</option>
            {purchaseOrders.map((order) => (
              <option key={order.purchase_order_id} value={order.purchase_order_id}>
                {order.order_number} · {order.store_name} · {order.supplier_name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Store
          <select
            name="store_id"
            value={form.store_id}
            onChange={onChange}
            required
            disabled={Boolean(selectedOrder)}
          >
            <option value="">Select store</option>
            {stores.map((store) => (
              <option key={store.storeid} value={store.storeid}>
                {store.storename}
              </option>
            ))}
          </select>
        </label>

        <label>
          Supplier
          <select
            name="supplier_id"
            value={form.supplier_id}
            onChange={onChange}
            required
            disabled={Boolean(selectedOrder)}
          >
            <option value="">Select supplier</option>
            {suppliers.map((supplier) => (
              <option
                key={supplier.supplierid}
                value={supplier.supplierid}
              >
                {supplier.suppliername}
              </option>
            ))}
          </select>
        </label>

        <label>
          Supplier invoice number
          <input
            name="invoice_number"
            value={form.invoice_number}
            onChange={onChange}
            maxLength={20}
            required
          />
        </label>

        <label>
          Invoice date
          <input
            type="date"
            name="invoice_date"
            value={form.invoice_date}
            onChange={onChange}
            required
          />
        </label>

        <label>
          Purchase date
          <input
            type="date"
            name="purchase_date"
            value={form.purchase_date}
            onChange={onChange}
            required
          />
        </label>

        <label>
          GRN number
          <input
            name="grn_number"
            value={form.grn_number}
            onChange={onChange}
            maxLength={50}
            required
          />
        </label>

        <label>
          Goods received date
          <input
            type="date"
            name="grn_date"
            value={form.grn_date}
            onChange={onChange}
            required
          />
        </label>

        <label className="receiving-full-width">
          Remarks
          <textarea
            name="remarks"
            value={form.remarks}
            onChange={onChange}
            maxLength={255}
            rows={3}
            placeholder="Condition of goods or delivery notes"
          />
        </label>
      </div>
    </section>
  )
}