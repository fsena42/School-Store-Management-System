
import { useState } from 'react'
import StaffManagement from './StaffManagement'
import ItemManagement from './ItemManagement'
import SupplierManagement from './SupplierManagement'
import './ManagementPage.css'

const sections = [
  { id: 'staff', label: 'Staff' },
  { id: 'items', label: 'Inventory items' },
  { id: 'suppliers', label: 'Suppliers' },
]

export default function ManagementPage({ onBack }) {
  const [active, setActive] = useState('staff')

  return (
    <main className="management-page">
      <header className="management-header">
        <div>
          <h1>Management</h1>
          <p>Manage staff, inventory items and suppliers.</p>
        </div>

        <button className="management-back" onClick={onBack}>
          Back to dashboard
        </button>
      </header>

      <nav className="management-tabs">
        {sections.map((section) => (
          <button
            key={section.id}
            className={active === section.id ? 'active' : ''}
            onClick={() => setActive(section.id)}
          >
            {section.label}
          </button>
        ))}
      </nav>

      {active === 'staff' && <StaffManagement />}
      {active === 'items' && <ItemManagement />}
      {active === 'suppliers' && <SupplierManagement />}
    </main>
  )
}
