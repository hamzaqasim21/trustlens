import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Settings.css'

function Settings() {
  return (
    <div className="settings-page">
      <Navbar />

      <div className="settings-hero">
        <div className="settings-hero-shape"></div>
        <div className="settings-eyebrow">ACCOUNT</div>
        <h1 className="settings-title">Manage your account</h1>
      </div>

      <div className="settings-content">
        <div className="settings-card">
          <div className="settings-card-header">
            <span className="settings-card-tag tag-green">PROFILE</span>
            <h2>Personal details</h2>
          </div>
          <div className="settings-field">
            <label>Full name</label>
            <input type="text" defaultValue="Hamza Qasim" />
          </div>
          <div className="settings-field">
            <label>Email</label>
            <input type="email" defaultValue="hamza@example.com" />
          </div>
          <button className="settings-save">Save changes</button>
        </div>

        <div className="settings-card">
          <div className="settings-card-header">
            <span className="settings-card-tag tag-amber">SECURITY</span>
            <h2>Password</h2>
          </div>
          <div className="settings-field">
            <label>Current password</label>
            <input type="password" placeholder="••••••••" />
          </div>
          <div className="settings-field">
            <label>New password</label>
            <input type="password" placeholder="••••••••" />
          </div>
          <button className="settings-save">Update password</button>
        </div>

        <div className="settings-card card-danger">
          <div className="settings-card-header">
            <span className="settings-card-tag tag-red">DANGER ZONE</span>
            <h2>Delete account</h2>
          </div>
          <p className="settings-danger-text">
            This permanently deletes your scan history and account. This cannot be undone.
          </p>
          <button className="settings-delete">Delete my account</button>
        </div>
      </div>
    </div>
  )
}

export default Settings