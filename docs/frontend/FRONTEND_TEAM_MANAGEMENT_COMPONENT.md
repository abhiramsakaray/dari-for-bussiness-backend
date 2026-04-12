# Complete Frontend Team Management Component

## Direct Account Creation (No Invitation)

This component creates team member accounts directly with passwords - no email invitation needed.

---

## Complete React Component

```typescript
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

interface TeamMember {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  invite_pending: boolean;
  last_login: string | null;
  created_at: string;
}

interface CreateMemberResult {
  id: string;
  email: string;
  name: string;
  role: string;
  temporary_password?: string;
  message: string;
}

export const TeamManagement: React.FC = () => {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  // Form state
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('developer');
  const [autoGenerate, setAutoGenerate] = useState(true);
  const [customPassword, setCustomPassword] = useState('');
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState<CreateMemberResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchMembers();
  }, []);

  const fetchMembers = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/team`, {
        params: { page: 1, page_size: 50 },
      });
      setMembers(response.data.members || []);
    } catch (err) {
      console.error('Failed to fetch members:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setCreating(true);

    try {
      const token = localStorage.getItem('access_token');
      
      const payload: any = {
        email: email.toLowerCase(),
        name,
        role,
      };

      if (autoGenerate) {
        payload.auto_generate_password = true;
      } else {
        if (!customPassword) {
          setError('Password is required');
          setCreating(false);
          return;
        }
        payload.password = customPassword;
      }

      const response = await axios.post(
        `${API_BASE_URL}/team/members`,
        payload,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setCreateResult(response.data);
      
      // Refresh member list
      await fetchMembers();
      
      // Reset form
      setEmail('');
      setName('');
      setRole('developer');
      setCustomPassword('');
      setAutoGenerate(true);
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create team member');
    } finally {
      setCreating(false);
    }
  };

  const closeModal = () => {
    setShowCreateModal(false);
    setCreateResult(null);
    setError('');
  };

  const getStatusBadge = (member: TeamMember) => {
    if (!member.is_active) {
      return <span className="badge badge-inactive">Inactive</span>;
    }
    if (member.invite_pending) {
      return <span className="badge badge-pending">Pending Setup</span>;
    }
    if (member.last_login) {
      return <span className="badge badge-active">Active</span>;
    }
    return <span className="badge badge-new">Never Logged In</span>;
  };

  const getRoleColor = (role: string) => {
    const colors: Record<string, string> = {
      owner: 'purple',
      admin: 'blue',
      developer: 'green',
      finance: 'orange',
      viewer: 'gray',
    };
    return colors[role.toLowerCase()] || 'gray';
  };

  if (loading) {
    return <div className="loading">Loading team members...</div>;
  }

  return (
    <div className="team-management">
      <div className="header">
        <div>
          <h1>Team Management</h1>
          <p>Manage members, permissions, and sessions</p>
        </div>
        <button 
          className="btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          + Create Member Account
        </button>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{members.length}</div>
          <div className="stat-label">Total Members</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {members.filter(m => m.is_active && !m.invite_pending).length}
          </div>
          <div className="stat-label">Active</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {members.filter(m => m.invite_pending).length}
          </div>
          <div className="stat-label">Pending Setup</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {members.filter(m => m.is_active && m.last_login).length}
          </div>
          <div className="stat-label">Logged In</div>
        </div>
      </div>

      {/* Members Table */}
      <div className="members-table">
        <table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last Login</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-state">
                  <div>
                    <p>No team members yet</p>
                    <button onClick={() => setShowCreateModal(true)}>
                      Create First Member
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              members.map((member) => (
                <tr key={member.id}>
                  <td>
                    <div className="member-info">
                      <div className="member-avatar">
                        {member.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="member-name">{member.name}</div>
                        <div className="member-email">{member.email}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span 
                      className={`role-badge role-${getRoleColor(member.role)}`}
                    >
                      {member.role}
                    </span>
                  </td>
                  <td>{getStatusBadge(member)}</td>
                  <td>
                    {member.last_login
                      ? new Date(member.last_login).toLocaleDateString()
                      : 'Never'}
                  </td>
                  <td>
                    <button className="btn-sm">Edit</button>
                    <button className="btn-sm btn-danger">Remove</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create Member Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create Team Member Account</h2>
              <button className="close-btn" onClick={closeModal}>×</button>
            </div>

            {createResult ? (
              <div className="modal-body">
                <div className="success-message">
                  <div className="success-icon">✓</div>
                  <h3>Account Created Successfully!</h3>
                  <p>{createResult.message}</p>

                  <div className="account-details">
                    <div className="detail-row">
                      <span className="label">Email:</span>
                      <span className="value">{createResult.email}</span>
                    </div>
                    <div className="detail-row">
                      <span className="label">Name:</span>
                      <span className="value">{createResult.name}</span>
                    </div>
                    <div className="detail-row">
                      <span className="label">Role:</span>
                      <span className="value">{createResult.role}</span>
                    </div>
                  </div>

                  {createResult.temporary_password && (
                    <div className="password-box">
                      <div className="password-header">
                        <strong>⚠️ Temporary Password</strong>
                        <button
                          className="copy-btn"
                          onClick={() => {
                            navigator.clipboard.writeText(createResult.temporary_password!);
                            alert('Password copied to clipboard!');
                          }}
                        >
                          Copy
                        </button>
                      </div>
                      <code className="password-code">
                        {createResult.temporary_password}
                      </code>
                      <p className="password-warning">
                        ⚠️ Save this password! Share it securely with the team member.
                        They can login immediately at: <strong>/login</strong>
                      </p>
                    </div>
                  )}

                  <div className="next-steps">
                    <h4>Next Steps:</h4>
                    <ol>
                      <li>Share the login credentials with the team member</li>
                      <li>They can login at <code>/login</code></li>
                      <li>Recommend they change their password after first login</li>
                    </ol>
                  </div>
                </div>

                <div className="modal-footer">
                  <button className="btn-primary" onClick={closeModal}>
                    Done
                  </button>
                  <button 
                    className="btn-secondary"
                    onClick={() => {
                      setCreateResult(null);
                      setEmail('');
                      setName('');
                    }}
                  >
                    Create Another
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateMember}>
                <div className="modal-body">
                  <div className="form-group">
                    <label>Email Address *</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="member@example.com"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label>Full Name *</label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="John Doe"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label>Role *</label>
                    <select value={role} onChange={(e) => setRole(e.target.value)}>
                      <option value="admin">Admin - Manage team & all features</option>
                      <option value="developer">Developer - API keys & integrations</option>
                      <option value="finance">Finance - Payments & financial data</option>
                      <option value="viewer">Viewer - Read-only access</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={autoGenerate}
                        onChange={(e) => setAutoGenerate(e.target.checked)}
                      />
                      <span>Auto-generate secure password (Recommended)</span>
                    </label>
                  </div>

                  {!autoGenerate && (
                    <div className="form-group">
                      <label>Custom Password *</label>
                      <input
                        type="password"
                        value={customPassword}
                        onChange={(e) => setCustomPassword(e.target.value)}
                        placeholder="Min 8 chars, uppercase, lowercase, number, special"
                        required={!autoGenerate}
                      />
                      <small className="help-text">
                        Must contain: 8+ characters, uppercase, lowercase, number, special character
                      </small>
                    </div>
                  )}

                  {error && (
                    <div className="error-message">
                      {error}
                    </div>
                  )}
                </div>

                <div className="modal-footer">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={closeModal}
                    disabled={creating}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={creating}
                  >
                    {creating ? 'Creating...' : 'Create Account'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TeamManagement;
```

---

## CSS Styles

```css
.team-management {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px 0;
}

.header p {
  color: #666;
  margin: 0;
}

.btn-primary {
  background: #4F46E5;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary:hover {
  background: #4338CA;
}

.btn-primary:disabled {
  background: #9CA3AF;
  cursor: not-allowed;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 20px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #6B7280;
}

/* Table */
.members-table {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  overflow: hidden;
}

table {
  width: 100%;
  border-collapse: collapse;
}

thead {
  background: #F9FAFB;
  border-bottom: 1px solid #E5E7EB;
}

th {
  text-align: left;
  padding: 12px 16px;
  font-weight: 600;
  font-size: 14px;
  color: #374151;
}

td {
  padding: 16px;
  border-bottom: 1px solid #F3F4F6;
}

tr:last-child td {
  border-bottom: none;
}

.member-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.member-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #4F46E5;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.member-name {
  font-weight: 500;
  color: #111827;
}

.member-email {
  font-size: 14px;
  color: #6B7280;
}

/* Badges */
.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge-active {
  background: #D1FAE5;
  color: #065F46;
}

.badge-pending {
  background: #FEF3C7;
  color: #92400E;
}

.badge-inactive {
  background: #F3F4F6;
  color: #6B7280;
}

.badge-new {
  background: #DBEAFE;
  color: #1E40AF;
}

.role-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: capitalize;
}

.role-purple { background: #EDE9FE; color: #6B21A8; }
.role-blue { background: #DBEAFE; color: #1E40AF; }
.role-green { background: #D1FAE5; color: #065F46; }
.role-orange { background: #FED7AA; color: #9A3412; }
.role-gray { background: #F3F4F6; color: #374151; }

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #E5E7EB;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  color: #9CA3AF;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
}

.modal-body {
  padding: 24px;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #E5E7EB;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* Form */
.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-weight: 500;
  margin-bottom: 8px;
  color: #374151;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #D1D5DB;
  border-radius: 6px;
  font-size: 14px;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
}

.help-text {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #6B7280;
}

/* Success Message */
.success-message {
  text-align: center;
}

.success-icon {
  width: 64px;
  height: 64px;
  background: #D1FAE5;
  color: #065F46;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  margin: 0 auto 16px;
}

.success-message h3 {
  margin: 0 0 8px 0;
  font-size: 20px;
}

.account-details {
  background: #F9FAFB;
  border-radius: 8px;
  padding: 16px;
  margin: 24px 0;
  text-align: left;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #E5E7EB;
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row .label {
  font-weight: 500;
  color: #6B7280;
}

.detail-row .value {
  color: #111827;
}

/* Password Box */
.password-box {
  background: #FEF3C7;
  border: 2px solid #F59E0B;
  border-radius: 8px;
  padding: 16px;
  margin: 24px 0;
  text-align: left;
}

.password-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.copy-btn {
  background: #F59E0B;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.password-code {
  display: block;
  background: white;
  padding: 12px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 12px;
  word-break: break-all;
}

.password-warning {
  font-size: 13px;
  color: #92400E;
  margin: 0;
}

/* Next Steps */
.next-steps {
  background: #F9FAFB;
  border-radius: 8px;
  padding: 16px;
  margin-top: 24px;
  text-align: left;
}

.next-steps h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
}

.next-steps ol {
  margin: 0;
  padding-left: 20px;
}

.next-steps li {
  margin-bottom: 8px;
  font-size: 14px;
  color: #374151;
}

.next-steps code {
  background: #E5E7EB;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
}

/* Error Message */
.error-message {
  background: #FEE2E2;
  border: 1px solid #EF4444;
  color: #991B1B;
  padding: 12px;
  border-radius: 6px;
  margin-top: 16px;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 48px 24px;
}

.empty-state p {
  color: #6B7280;
  margin-bottom: 16px;
}

/* Buttons */
.btn-secondary {
  background: white;
  color: #374151;
  border: 1px solid #D1D5DB;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #F9FAFB;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #D1D5DB;
  background: white;
  cursor: pointer;
  margin-right: 8px;
}

.btn-sm:hover {
  background: #F9FAFB;
}

.btn-danger {
  color: #DC2626;
  border-color: #FCA5A5;
}

.btn-danger:hover {
  background: #FEE2E2;
}
```

---

## Status Indicators Explained

| Status | Meaning | When Shown |
|--------|---------|------------|
| **Active** | Member has logged in | `is_active: true` AND `last_login` exists |
| **Never Logged In** | Account created but never used | `is_active: true` AND `last_login: null` AND `invite_pending: false` |
| **Pending Setup** | Invitation sent, not accepted | `invite_pending: true` |
| **Inactive** | Account deactivated | `is_active: false` |

---

## Key Features

✅ **Direct Account Creation** - No email invitation needed  
✅ **Auto-Generate Password** - Secure random passwords  
✅ **Custom Password** - Admin can set specific password  
✅ **Status Indicators** - Clear visual status for each member  
✅ **Copy Password** - One-click copy to clipboard  
✅ **Success Modal** - Shows credentials after creation  
✅ **Member Stats** - Total, Active, Pending, Logged In counts  
✅ **Role Badges** - Color-coded role indicators  

---

## Usage

```typescript
import TeamManagement from './components/TeamManagement';

function App() {
  return (
    <div>
      <TeamManagement />
    </div>
  );
}
```

---

**This component uses the RBAC endpoint `POST /team/members` for direct account creation with proper status tracking!**
