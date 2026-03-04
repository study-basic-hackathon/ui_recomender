import { useState, useEffect, useRef, useCallback } from 'react'

export interface LogEntry {
  job_type: string
  proposal_index: number | null
  phase: string
  message: string
  detail?: string
  timestamp?: string
}

export interface JobLogState {
  phase: string
  entries: LogEntry[]
}

export interface LogStreamState {
  /** Map of jobKey -> log state. jobKey = `${job_type}` or `${job_type}:${proposal_index}` */
  jobs: Map<string, JobLogState>
  isStreaming: boolean
  isDone: boolean
}

const MAX_ENTRIES_PER_JOB = 5000

function jobKey(entry: LogEntry): string {
  if (entry.proposal_index != null) {
    return `${entry.job_type}:${entry.proposal_index}`
  }
  return entry.job_type
}

export function useLogStream(sessionId: string | null, enabled: boolean): LogStreamState {
  const [state, setState] = useState<LogStreamState>({
    jobs: new Map(),
    isStreaming: false,
    isDone: false,
  })
  const eventSourceRef = useRef<EventSource | null>(null)
  const jobsRef = useRef<Map<string, JobLogState>>(new Map())
  const connectedOnceRef = useRef(false)
  const enabledRef = useRef(enabled)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [reconnectCount, setReconnectCount] = useState(0)

  // Keep enabledRef in sync
  enabledRef.current = enabled

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  // Reset connectedOnceRef when sessionId changes
  useEffect(() => {
    connectedOnceRef.current = false
  }, [sessionId])

  useEffect(() => {
    if (!sessionId || !enabled) {
      cleanup()
      return
    }

    // On reconnect after done, preserve existing logs
    const isReconnect = connectedOnceRef.current
    if (!isReconnect) {
      jobsRef.current = new Map()
      setState({ jobs: new Map(), isStreaming: true, isDone: false })
    } else {
      setState((prev) => ({ ...prev, isStreaming: true, isDone: false }))
    }

    // On reconnect (2nd+ connection), skip old logs by requesting only recent ones
    const url = isReconnect
      ? `/api/sessions/${sessionId}/logs/stream?since_seconds=1`
      : `/api/sessions/${sessionId}/logs/stream`
    connectedOnceRef.current = true

    const es = new EventSource(url)
    eventSourceRef.current = es

    es.addEventListener('log', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as LogEntry
        // Skip keepalive events
        if (data.job_type === '_keepalive') return

        const key = jobKey(data)
        const current = jobsRef.current.get(key) || { phase: 'pending', entries: [] }

        // Update phase
        current.phase = data.phase

        // Append entry with rotation
        current.entries.push(data)
        if (current.entries.length > MAX_ENTRIES_PER_JOB) {
          current.entries = current.entries.slice(-MAX_ENTRIES_PER_JOB)
        }

        jobsRef.current.set(key, current)
        setState({
          jobs: new Map(jobsRef.current),
          isStreaming: true,
          isDone: false,
        })
      } catch {
        // Ignore parse errors
      }
    })

    es.addEventListener('done', () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      // If still enabled (iteration in progress), auto-reconnect after delay
      if (enabledRef.current) {
        setState((prev) => ({ ...prev, isStreaming: false }))
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          setReconnectCount((c) => c + 1)
        }, 2000)
      } else {
        setState((prev) => ({ ...prev, isStreaming: false, isDone: true }))
      }
    })

    es.onerror = () => {
      // EventSource will auto-reconnect for network errors
      // If readyState is CLOSED, the connection has been permanently closed
      if (es.readyState === EventSource.CLOSED) {
        setState((prev) => ({
          ...prev,
          isStreaming: false,
        }))
      }
    }

    return cleanup
  }, [sessionId, enabled, cleanup, reconnectCount])

  return state
}
