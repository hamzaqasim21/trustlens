import { ACCOUNT_TYPES } from '../lib/accountTypes'
import './AccountTypePicker.css'

function AccountTypePicker({ value, onChange, disabled = false, name = 'account-type', stacked = false }) {
  return (
    <div className={`atp ${stacked ? 'atp-stacked' : ''}`} role="radiogroup" aria-label="Account type">
      {ACCOUNT_TYPES.map((t) => (
        <label key={t.id} className={`atp-option ${value === t.id ? 'is-on' : ''}`}>
          <input
            type="radio"
            name={name}
            value={t.id}
            checked={value === t.id}
            onChange={() => onChange(t.id)}
            disabled={disabled}
          />
          <strong>{t.label}</strong>
          <span>{t.text}</span>
        </label>
      ))}
    </div>
  )
}

export default AccountTypePicker
