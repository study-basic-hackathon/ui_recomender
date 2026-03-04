import { useState, useRef, useEffect, useCallback } from 'react'
import type { LogStreamState, JobLogState, LogEntry } from '../hooks/useLogStream'

const PHASE_LABELS: Record<string, string> = {
  cloning: 'Cloning',
  patching: 'Applying Patch',
  screenshot: 'Taking Screenshot',
  analyzing: 'Analyzing',
  implementing: 'Implementing',
  uploading: 'Uploading',
  pushing: 'Pushing',
  creating_pr: 'Creating PR',
  completed: 'Completed',
  waiting: 'Waiting',
  running: 'Running',
  error: 'Error',
}

const JOB_TYPE_LABELS: Record<string, string> = {
  analyze: 'Analyze',
  implement: 'Implement',
  createpr: 'Create PR',
}

function getPhaseLabel(phase: string): string {
  return PHASE_LABELS[phase] || phase
}

function getJobLabel(jobKey: string): string {
  const [jobType, indexStr] = jobKey.split(':')
  const base = JOB_TYPE_LABELS[jobType] || jobType
  if (indexStr != null) {
    return `${base} #${Number(indexStr) + 1}`
  }
  return base
}

function getOverallPhase(logState: LogStreamState): string {
  // Find the most recent active phase across all jobs
  let latestPhase = 'waiting'
  for (const [, job] of logState.jobs) {
    if (job.phase === 'completed') continue
    if (job.phase === 'error') return 'error'
    latestPhase = job.phase
  }
  // If all are completed
  const allCompleted = logState.jobs.size > 0 && [...logState.jobs.values()].every((j) => j.phase === 'completed')
  if (allCompleted) return 'completed'
  return latestPhase
}

const ROW_HEIGHT = 20

interface LogViewerProps {
  entries: LogEntry[]
}

function LogViewer({ entries }: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [autoScroll, setAutoScroll] = useState(true)

  const totalHeight = entries.length * ROW_HEIGHT
  const containerHeight = 300

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = totalHeight - containerHeight
    }
  }, [entries.length, autoScroll, totalHeight])

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop: st, scrollHeight, clientHeight } = containerRef.current
    setScrollTop(st)
    // If user scrolls near the bottom, re-enable auto-scroll
    const isNearBottom = scrollHeight - st - clientHeight < ROW_HEIGHT * 3
    setAutoScroll(isNearBottom)
  }, [])

  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 5)
  const endIndex = Math.min(entries.length, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + 5)
  const visibleEntries = entries.slice(startIndex, endIndex)

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{
        height: `${containerHeight}px`,
        overflow: 'auto',
        position: 'relative',
        backgroundColor: '#0d1117',
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
        fontSize: '12px',
        lineHeight: `${ROW_HEIGHT}px`,
      }}
    >
      <div style={{ height: `${totalHeight}px`, position: 'relative' }}>
        {visibleEntries.map((entry, i) => {
          const index = startIndex + i
          const time = entry.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString()
            : ''
          return (
            <div
              key={index}
              style={{
                position: 'absolute',
                top: `${index * ROW_HEIGHT}px`,
                left: 0,
                right: 0,
                height: `${ROW_HEIGHT}px`,
                padding: '0 8px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                color: entry.phase === 'error' ? '#f87171' : '#c9d1d9',
              }}
            >
              <span style={{ color: '#6e7681', marginRight: '8px' }}>{time}</span>
              <span>{entry.message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface LogPanelProps {
  logState: LogStreamState
}

export default function LogPanel({ logState }: LogPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [activeTab, setActiveTab] = useState<string | null>(null)

  const jobKeys = [...logState.jobs.keys()]

  // Auto-select first tab
  useEffect(() => {
    if (activeTab === null && jobKeys.length > 0) {
      setActiveTab(jobKeys[0])
    }
  }, [jobKeys.length, activeTab, jobKeys])

  const overallPhase = getOverallPhase(logState)
  const phaseLabel = getPhaseLabel(overallPhase)

  const activeJobState: JobLogState | undefined =
    activeTab ? logState.jobs.get(activeTab) : undefined

  const dotColor =
    overallPhase === 'completed'
      ? '#34d399'
      : overallPhase === 'error'
        ? '#f87171'
        : '#60a5fa'

  return (
    <div
      style={{
        borderRadius: '8px',
        border: '1px solid #30363d',
        overflow: 'hidden',
        marginBottom: '16px',
        backgroundColor: '#161b22',
      }}
    >
      {/* Status line */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          backgroundColor: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: '#c9d1d9',
          fontSize: '14px',
          fontWeight: 500,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: dotColor,
              display: 'inline-block',
              animation:
                overallPhase !== 'completed' && overallPhase !== 'error'
                  ? 'pulse 2s infinite'
                  : 'none',
            }}
          />
          {phaseLabel}
          {logState.isStreaming && overallPhase !== 'completed' && '...'}
        </span>
        <span style={{ color: '#6e7681', fontSize: '12px' }}>
          {expanded ? 'Hide' : 'Details'}
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div>
          {/* Tab bar (show only if multiple jobs) */}
          {jobKeys.length > 1 && (
            <div
              style={{
                display: 'flex',
                gap: '0',
                borderBottom: '1px solid #30363d',
                padding: '0 8px',
              }}
            >
              {jobKeys.map((key) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  style={{
                    padding: '8px 16px',
                    border: 'none',
                    borderBottom:
                      activeTab === key ? '2px solid #58a6ff' : '2px solid transparent',
                    backgroundColor: 'transparent',
                    color: activeTab === key ? '#c9d1d9' : '#6e7681',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: activeTab === key ? 600 : 400,
                  }}
                >
                  {getJobLabel(key)}
                </button>
              ))}
            </div>
          )}

          {/* Log viewer */}
          {activeJobState ? (
            <LogViewer entries={activeJobState.entries} />
          ) : (
            <div
              style={{
                height: '100px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#6e7681',
                fontSize: '13px',
              }}
            >
              Waiting for logs...
            </div>
          )}
        </div>
      )}

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
