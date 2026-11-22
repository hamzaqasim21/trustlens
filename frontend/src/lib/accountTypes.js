// The three kinds of user the scope document describes (§10). Kept in one
// place so Sign up, Settings and the navigation always agree.
export const ACCOUNT_TYPES = [
  { id: 'personal', label: 'Personal', text: 'Check accounts before you trust them, and watch them for score drops.' },
  { id: 'creator', label: 'Creator', text: 'Prove your account is yours, see your audience report, get a Trust Badge.' },
  { id: 'brand', label: 'Brand / agency', text: 'Bulk-check influencers, export CSV and PDF reports, use the API.' },
]

export const ACCOUNT_TYPE_LABEL = Object.fromEntries(ACCOUNT_TYPES.map((t) => [t.id, t.label]))
