import { useState, useEffect, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import { listSessions, type Session } from '../services/api'
import Sidebar from './Sidebar'

type LayoutContext = {
  refreshSessions: () => void
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sessions, setSessions] = useState<Session[]>([])

  const refreshSessions = useCallback(() => {
    listSessions()
      .then(setSessions)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshSessions()
  }, [refreshSessions])

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar sessions={sessions} isOpen={sidebarOpen} onToggle={() => setSidebarOpen(false)} />
      <div
        style={{
          flex: 1,
          marginLeft: sidebarOpen ? '350px' : '0px',
          transition: 'margin-left 0.2s ease',
          minHeight: '100vh',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: '30px', color: '#9ca3af' }}>☰</span>
            </button>
          )}
          <span style={{ fontSize: '26px', fontWeight: 600, color: 'rgba(255,255,255,0.87)' }}>
            UI Recommender
          </span>
        </div>
        <Outlet context={{ refreshSessions } satisfies LayoutContext} />
      </div>
    </div>
  )
}
