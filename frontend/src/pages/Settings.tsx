import { useState, useEffect } from 'react'
import { getSettings, saveSetting } from '../services/api'

export default function Settings() {
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    getSettings()
      .then((settings) => {
        for (const s of settings) {
          if (s.key === 'repo_url') setRepoUrl(s.value)
          if (s.key === 'branch') setBranch(s.value)
        }
      })
      .catch(() => {})
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    setMessage(null)

    try {
      await saveSetting('repo_url', repoUrl)
      await saveSetting('branch', branch || 'main')
      setMessage({ type: 'success', text: 'Settings saved.' })
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div style={{ maxWidth: '600px', margin: '0 auto', padding: '24px' }}>
      <h1 style={{ fontSize: '20px', marginBottom: '24px' }}>Settings</h1>

      <form onSubmit={handleSave}>
        <div style={{ marginBottom: '16px' }}>
          <label
            style={{ display: 'block', marginBottom: '4px', fontSize: '16px', fontWeight: 600 }}
          >
            Repository URL
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            required
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #4b5563',
              borderRadius: '6px',
              fontSize: '16px',
              boxSizing: 'border-box',
              backgroundColor: '#1a1a1a',
              color: 'rgba(255,255,255,0.87)',
            }}
          />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label
            style={{ display: 'block', marginBottom: '4px', fontSize: '16px', fontWeight: 600 }}
          >
            Branch
          </label>
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="main"
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #4b5563',
              borderRadius: '6px',
              fontSize: '16px',
              boxSizing: 'border-box',
              backgroundColor: '#1a1a1a',
              color: 'rgba(255,255,255,0.87)',
            }}
          />
        </div>

        {message && (
          <p
            style={{
              fontSize: '16px',
              marginBottom: '12px',
              color: message.type === 'success' ? '#34d399' : '#f87171',
            }}
          >
            {message.text}
          </p>
        )}

        <button
          type="submit"
          disabled={isSaving || !repoUrl}
          style={{
            padding: '10px 24px',
            backgroundColor: isSaving ? '#4b5563' : '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '16px',
            fontWeight: 600,
            cursor: isSaving ? 'not-allowed' : 'pointer',
          }}
        >
          {isSaving ? 'Saving...' : 'Save Settings'}
        </button>
      </form>
    </div>
  )
}
