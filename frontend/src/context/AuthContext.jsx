import { createContext, useContext, useEffect, useState } from 'react'
import { signup as apiSignup, login as apiLogin, verifyEmail, getCurrentUser } from '../api/trustlens'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // True after the user presses "Log out" on purpose (until they next log
  // in). Members-only pages use it to send them home rather than to the
  // login screen: logging out of Settings shouldn't ask you to log back in.
  const [signedOut, setSignedOut] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('trustlens_token')
    if (!token) {
      setLoading(false)
      return
    }
    getCurrentUser(token)
      .then(setUser)
      .catch(() => localStorage.removeItem('trustlens_token'))
      .finally(() => setLoading(false))
  }, [])

  function _completeLogin(token, user) {
    localStorage.setItem('trustlens_token', token)
    setSignedOut(false)
    setUser(user)
  }

  // Password check. Normally logs in directly ({ token, user }). If the
  // account was never verified (e.g. they closed the tab during signup),
  // the backend instead resends a code and returns { requires_verification,
  // email, message } — same shape signup() returns in that case.
  async function login(email, password) {
    const result = await apiLogin(email, password)
    if (result.token) {
      _completeLogin(result.token, result.user)
    }
    return result
  }

  // Creates the account. Never logs in directly — always returns
  // { requires_verification, email, message }; verifyCode() finishes it.
  async function signup(fullName, email, password, accountType) {
    return apiSignup(fullName, email, password, accountType)
  }

  // Confirms the emailed code — for both a fresh signup and a resent code
  // from an unverified login attempt. This is the only thing that can turn
  // an unverified account into a logged-in session.
  async function verifyCode(email, code) {
    const { token, user } = await verifyEmail(email, code)
    _completeLogin(token, user)
  }

  function logout() {
    localStorage.removeItem('trustlens_token')
    setSignedOut(true)
    setUser(null)
  }

  // After Settings changes the name, the navbar should show it straight
  // away without a reload. Only fields the server returned are applied.
  function applyUserUpdate(updated) {
    setUser((prev) => (prev ? { ...prev, ...updated } : prev))
  }

  return (
    <AuthContext.Provider value={{ user, loading, signedOut, login, signup, verifyCode, logout, applyUserUpdate }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
