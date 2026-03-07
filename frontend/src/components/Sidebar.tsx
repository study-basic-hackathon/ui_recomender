import { useNavigate, useLocation } from 'react-router-dom'
import { type Session } from '../services/api'
import StatusBadge from './StatusBadge'
import logoIcon from '../assets/claude_desgin.png'

type SidebarProps = {
  sessions: Session[]
  isOpen: boolean
  onToggle: () => void
}

function getSessionStatus(session: Session): string {
  if (session.iterations.length === 0) return 'pending'
  const latest = session.iterations[session.iterations.length - 1]
  return latest.status
}

function getSessionInstruction(session: Session): string {
  if (session.iterations.length === 0) return ''
  return session.iterations[0].instruction
}

export default function Sidebar({ sessions, isOpen, onToggle }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div
      style={{
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
        width: isOpen ? '350px' : '0px',
        backgroundColor: '#1a1a1a',
        borderRight: '1px solid #374151',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        zIndex: 100,
      }}
    >
      <div
        style={{
          width: '350px',
          minWidth: '350px',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
        }}
      >
        <div
          style={{
            padding: '12px 16px 10px 16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <img
            src={logoIcon}
            alt="UI Recommender"
            style={{ height: '40px', width: '40px', mixBlendMode: 'screen' }}
          />
          <button
            onClick={onToggle}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <svg
              width="30"
              height="30"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#9ca3af"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="18" height="18" rx="3" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
        </div>

        <div
          style={{
            padding: '0 16px',
            height: '63px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <button
            onClick={() => navigate('/')}
            style={{
              width: '100%',
              padding: '10px 16px',
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            + New Session
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {sessions.map((session) => {
            const isActive = location.pathname === `/sessions/${session.id}`
            const instruction = getSessionInstruction(session)
            const status = getSessionStatus(session)
            return (
              <div
                key={session.id}
                onClick={() => navigate(`/sessions/${session.id}`)}
                style={{
                  padding: '0 12px',
                  height: '63px',
                  borderRadius: '6px',
                  marginBottom: '4px',
                  cursor: 'pointer',
                  backgroundColor: isActive ? '#374151' : 'transparent',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ overflow: 'hidden', flex: 1, marginRight: '8px' }}>
                  <div
                    style={{
                      fontSize: '14px',
                      fontWeight: 500,
                      color: 'rgba(255,255,255,0.87)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {session.repo_url.replace('https://github.com/', '')}
                  </div>
                  <div
                    style={{
                      fontSize: '13px',
                      color: '#9ca3af',
                      marginTop: '2px',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {instruction.substring(0, 80)}
                    {instruction.length > 80 ? '...' : ''}
                  </div>
                </div>
                <StatusBadge status={status} />
              </div>
            )
          })}
        </div>

        <div
          onClick={() => navigate('/settings')}
          style={{
            padding: '0 16px',
            height: '63px',
            borderTop: '1px solid #374151',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '16px',
            color: '#9ca3af',
            backgroundColor: location.pathname === '/settings' ? '#374151' : 'transparent',
          }}
        >
          <span style={{ fontSize: '30px' }}>⚙</span>
          Settings
        </div>
      </div>
    </div>
  )
}
