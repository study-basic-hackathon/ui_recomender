import { useState, useEffect, useRef, useCallback } from 'react'
import { getJob, type Job } from '../services/api'

const TERMINAL_STATUSES = ['analyzed', 'completed', 'failed']

export function useJobPolling(jobId: string | null, intervalMs: number = 3000) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const timerRef = useRef<number | null>(null)

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!jobId) {
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
        const data = await getJob(jobId)
        setJob(data)
        setIsLoading(false)

        if (TERMINAL_STATUSES.includes(data.status)) {
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
  }, [jobId, intervalMs, stopPolling])

  const refetch = useCallback(async () => {
    if (!jobId) return
    try {
      const data = await getJob(jobId)
      setJob(data)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [jobId])

  return { job, error, isLoading, refetch }
}
