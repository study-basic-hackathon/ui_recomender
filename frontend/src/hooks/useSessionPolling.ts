import { useState, useEffect, useRef, useCallback } from 'react'
import { getSession, type Session } from '../services/api'

function isTerminal(session: Session): boolean {
  if (session.iterations.length === 0) return false
  const latest = session.iterations[session.iterations.length - 1]
  // Terminal: latest iteration completed or failed, and no proposals are still implementing
  if (latest.status === 'failed') return true
  if (latest.status === 'completed') {
    const hasImplementing = latest.proposals.some((p) => p.status === 'implementing')
    return !hasImplementing
  }
  return false
}

export function useSessionPolling(sessionId: string | null, intervalMs: number = 3000) {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const timerRef = useRef<number | null>(null)

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const restartPolling = useCallback(() => {
    if (timerRef.current !== null || !sessionId) return
    const poll = async () => {
      try {
        const data = await getSession(sessionId)
        setSession(data)
        if (isTerminal(data)) {
          stopPolling()
        }
      } catch (e) {
        setError((e as Error).message)
      }
    }
    poll()
    timerRef.current = window.setInterval(poll, intervalMs)
  }, [sessionId, intervalMs, stopPolling])

  useEffect(() => {
    if (!sessionId) {
      return
    }

    let isFirstPoll = true
    const poll = async () => {
      if (isFirstPoll) {
        setIsLoading(true)
        setError(null)
        isFirstPoll = false
      }
      try {
        const data = await getSession(sessionId)
        setSession(data)
        setIsLoading(false)

        if (isTerminal(data)) {
          stopPolling()
        }
      } catch (e) {
        setError((e as Error).message)
        setIsLoading(false)
      }
    }

    poll()
    timerRef.current = window.setInterval(poll, intervalMs)

    return stopPolling
  }, [sessionId, intervalMs, stopPolling])

  const refetch = useCallback(async () => {
    if (!sessionId) return
    try {
      const data = await getSession(sessionId)
      setSession(data)
      if (!isTerminal(data) && timerRef.current === null) {
        restartPolling()
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }, [sessionId, restartPolling])

  return { session, error, isLoading, refetch }
}
