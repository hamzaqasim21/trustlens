// Buttons added to the Results page on 2026-09-28: download the scan as a
// PDF report, and watch the account for score drops.
import { useEffect, useState } from 'react'
import { downloadScanPdf, watchlistApi } from '../api/trustlens'
import './ResultExtras.css'

export function ReportActions({ result }) {
  const [pdfBusy, setPdfBusy] = useState(false)
  const [watch, setWatch] = useState({ loading: true, entry: null })
  const [msg, setMsg] = useState('')
  const username = result.username?.toLowerCase()

  useEffect(() => {
    let cancelled = false
    watchlistApi.list()
      .then((r) => { if (!cancelled) setWatch({ loading: false, entry: r.items.find((e) => e.username === username) || null }) })
      .catch(() => { if (!cancelled) setWatch({ loading: false, entry: null }) })
    return () => { cancelled = true }
  }, [username])

  async function pdf() {
    setPdfBusy(true)
    setMsg('')
    try {
      await downloadScanPdf(result.scan_id)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setPdfBusy(false)
    }
  }

  async function toggleWatch() {
    setMsg('')
    setWatch((w) => ({ ...w, loading: true }))
    try {
      if (watch.entry) {
        await watchlistApi.remove(watch.entry.id)
        setWatch({ loading: false, entry: null })
        setMsg(`Stopped watching @${result.username}.`)
      } else {
        const entry = await watchlistApi.add(result.username)
        setWatch({ loading: false, entry })
        setMsg(`Watching @${result.username}. You’ll get an alert if its score drops.`)
      }
    } catch (err) {
      setWatch((w) => ({ ...w, loading: false }))
      setMsg(err.message)
    }
  }

  return (
    <div className="rx-actions">
      {result.scan_id && (
        <button type="button" className="tl-btn tl-btn-ink tl-btn-sm" onClick={pdf} disabled={pdfBusy}>
          {pdfBusy ? 'Preparing PDF…' : 'Download PDF report'}
        </button>
      )}
      <button type="button" className="tl-btn tl-btn-outline tl-btn-sm" onClick={toggleWatch} disabled={watch.loading}
        aria-pressed={Boolean(watch.entry)}>
        {watch.entry ? 'Watching · stop' : 'Watch this account'}
      </button>
      {msg && <span className="rx-actions-msg" role="status">{msg}</span>}
    </div>
  )
}
