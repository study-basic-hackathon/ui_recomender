import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createSession, getSettings } from '../services/api'
import { useLayoutContext } from '../hooks/useLayoutContext'

export default function Dashboard() {
  const navigate = useNavigate()
  const { refreshSessions } = useLayoutContext()
  const [instruction, setInstruction] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [repoUrl, setRepoUrl] = useState<string | null>(null)
  const [branch, setBranch] = useState<string>('main')
  const [settingsLoaded, setSettingsLoaded] = useState(false)

  useEffect(() => {
    getSettings()
      .then((settings) => {
        for (const s of settings) {
          if (s.key === 'repo_url') setRepoUrl(s.value)
          if (s.key === 'branch') setBranch(s.value)
        }
        setSettingsLoaded(true)
      })
      .catch(() => {
        setSettingsLoaded(true)
      })
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoUrl || !instruction) return

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const session = await createSession({
        repo_url: repoUrl,
        branch: branch || 'main',
        instruction,
      })
      refreshSessions()
      navigate(`/sessions/${session.id}`)
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '24px' }}>
      {settingsLoaded && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#2a2a2a',
            border: '1px solid #4b5563',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '16px',
            color: '#9ca3af',
          }}
        >
          {repoUrl ? (
            <>
              {repoUrl.replace('https://github.com/', '')}
              <span style={{ marginLeft: '8px', color: '#6b7280' }}>({branch || 'main'})</span>
            </>
          ) : (
            <>
              Repository URL is not configured.{' '}
              <Link to="/settings" style={{ color: '#60a5fa', fontWeight: 600 }}>
                Go to Settings
              </Link>{' '}
              to set it up.
            </>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <h2
            style={{
              fontSize: '36px',
              fontWeight: 600,
              marginTop: '80px',
              marginBottom: '50px',
              textAlign: 'center',
            }}
          >
            どのようなデザインにしたいですか？
          </h2>
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Describe the UI changes you want..."
            required
            rows={4}
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #4b5563',
              borderRadius: '6px',
              fontSize: '16px',
              resize: 'vertical',
              boxSizing: 'border-box',
              backgroundColor: '#1a1a1a',
              color: 'rgba(255,255,255,0.87)',
            }}
          />
        </div>

        <p style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>
          あなたは AI によって実装・提案されたデザイン中から選択するだけです。 選択後、AI
          は修正を理解して PR を自動作成します。
        </p>

        {submitError && (
          <p style={{ color: '#f87171', fontSize: '16px', marginBottom: '12px' }}>{submitError}</p>
        )}

        <button
          type="submit"
          disabled={isSubmitting || !repoUrl || !instruction}
          style={{
            padding: '10px 24px',
            backgroundColor: isSubmitting || !repoUrl ? '#4b5563' : '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '16px',
            fontWeight: 600,
            cursor: isSubmitting || !repoUrl ? 'not-allowed' : 'pointer',
          }}
        >
          {isSubmitting ? 'Creating...' : 'Start Session'}
        </button>
      </form>
    </div>
  )
}
