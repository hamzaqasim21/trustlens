// Shown on the Creator studio / Brand tools pages to an account of another
// type. The server enforces the same rule on every endpoint (403); this only
// explains it and offers the switch, which is a real PATCH /me.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { setAccountType } from '../api/trustlens'
import { useAuth } from '../context/AuthContext'
import { ACCOUNT_TYPE_LABEL } from '../lib/accountTypes'

function RoleGate({ type, what }) {
  const { user, applyUserUpdate } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function switchType() {
    setBusy(true)
    setError('')
    try {
      applyUserUpdate(await setAccountType(type))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <section className="tl-band">
      <div className="tl-wrap-narrow">
        <div className="tl-empty">
          <h3>{what} are for {ACCOUNT_TYPE_LABEL[type].toLowerCase()} accounts</h3>
          <p>
            Your account is set to <strong>{ACCOUNT_TYPE_LABEL[user.account_type || 'personal']}</strong>. Switch it to use
            these tools. Your scans, watchlist and reports stay with you, and you can switch back in Settings at any time.
          </p>
          {error && <p className="tl-alert tl-alert-bad">{error}</p>}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
            <button className="tl-btn tl-btn-grad" onClick={switchType} disabled={busy}>
              {busy ? 'Switching…' : `Switch to a ${ACCOUNT_TYPE_LABEL[type]} account`}
            </button>
            <Link to="/dashboard" className="tl-btn tl-btn-outline">Back to dashboard</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

export default RoleGate
