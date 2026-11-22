import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ScrollManager from './components/site/ScrollManager'
import Landing from './pages/Landing'
import Login from './pages/Login'
import SignUp from './pages/SignUp'
import ScanPage from './pages/ScanPage'
import Dashboard from './pages/Dashboard'
import Results from './pages/Results'
import Comparison from './pages/Comparison'
import Settings from './pages/Settings'
import About from './pages/About'
import Methodology from './pages/Methodology'
import Extension from './pages/Extension'
import NotFound from './pages/NotFound'
import CreatorStudio from './pages/CreatorStudio'
import BrandTools from './pages/BrandTools'
import BadgeVerify from './pages/BadgeVerify'
import AdminLayout from './pages/admin/AdminLayout'
import AdminOverview from './pages/admin/AdminOverview'
import AdminAppeals from './pages/admin/AdminAppeals'
import AdminAppealDetail from './pages/admin/AdminAppealDetail'
import AdminUsers from './pages/admin/AdminUsers'
import AdminUserDetail from './pages/admin/AdminUserDetail'
import AdminScans from './pages/admin/AdminScans'
import AdminScanDetail from './pages/admin/AdminScanDetail'
import AdminSystem from './pages/admin/AdminSystem'
import AdminAudit from './pages/admin/AdminAudit'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollManager />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<SignUp />} />
          {/* The scan itself: a start form, or the live "scanning" screen
              when ?u= is set. Needs an account (so does the API). */}
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/results" element={<Results />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/comparison" element={<Comparison />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/about" element={<About />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/extension" element={<Extension />} />
          <Route path="/creator" element={<CreatorStudio />} />
          <Route path="/brand" element={<BrandTools />} />
          <Route path="/badge/:code" element={<BadgeVerify />} />

          {/* Admin console. AdminLayout shows a 403 to non-admins, and every
              /admin API call is independently checked on the server. */}
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOverview />} />
            <Route path="appeals" element={<AdminAppeals />} />
            <Route path="appeals/:id" element={<AdminAppealDetail />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="users/:id" element={<AdminUserDetail />} />
            <Route path="scans" element={<AdminScans />} />
            <Route path="scans/:id" element={<AdminScanDetail />} />
            <Route path="system" element={<AdminSystem />} />
            <Route path="audit" element={<AdminAudit />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
