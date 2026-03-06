import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useSessionPolling } from '../hooks/useSessionPolling'
import { useLogStream } from '../hooks/useLogStream'
import { createPR, iterate, getSession } from '../services/api'
import type { Iteration, Proposal } from '../services/api'
import { useLayoutContext } from '../hooks/useLayoutContext'
import StatusBadge from '../components/StatusBadge'
import ProposalCard from '../components/ProposalCard'
import LogPanel from '../components/LogPanel'

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const { refreshSessions } = useLayoutContext()
  const { session, error, isLoading, refetch } = useSessionPolling(sessionId ?? null)

  // Compute isInProgress early so useLogStream can be called unconditionally
  const latestIterationForHook =
    session && session.iterations.length > 0
      ? session.iterations[session.iterations.length - 1]
      : null
  const iterationStatusForHook = latestIterationForHook?.status ?? 'pending'
  const isInProgressForHook = ['pending', 'analyzing', 'implementing'].includes(
    iterationStatusForHook,
  )
  const logStreamState = useLogStream(sessionId ?? null, isInProgressForHook)

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [prLoading, setPrLoading] = useState(false)
  const [prError, setPrError] = useState<string | null>(null)
  const prPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [continueInstruction, setContinueInstruction] = useState('')
  const [continueLoading, setContinueLoading] = useState(false)
  const [continueError, setContinueError] = useState<string | null>(null)

  // Reset selection when session changes
  useEffect(() => {
    setSelectedIndex(null)
    setContinueInstruction('')
  }, [sessionId])

  const latestIteration: Iteration | null =
    session && session.iterations.length > 0
      ? session.iterations[session.iterations.length - 1]
      : null

  const toggleProposal = useCallback((index: number) => {
    setSelectedIndex((prev) => (prev === index ? null : index))
  }, [])

  const handleCreatePR = useCallback(async () => {
    if (selectedIndex === null || !sessionId || !latestIteration) return
    setPrLoading(true)
    setPrError(null)
    try {
      await createPR(sessionId, latestIteration.iteration_index, selectedIndex)
      refetch()
    } catch (e) {
      setPrError((e as Error).message)
    } finally {
      setPrLoading(false)
    }
  }, [selectedIndex, sessionId, latestIteration, refetch])

  const handleContinue = useCallback(async () => {
    if (selectedIndex === null || !sessionId || !continueInstruction.trim()) return
    setContinueLoading(true)
    setContinueError(null)
    try {
      await iterate(sessionId, selectedIndex, continueInstruction)
      refreshSessions()
      refetch()
      setContinueInstruction('')
      setSelectedIndex(null)
    } catch (e) {
      setContinueError((e as Error).message)
    } finally {
      setContinueLoading(false)
    }
  }, [selectedIndex, sessionId, continueInstruction, refreshSessions, refetch])

  // Poll for PR status changes
  useEffect(() => {
    if (!session || !sessionId || !latestIteration) return

    const hasCreating = latestIteration.proposals.some((p) => p.pr_status === 'creating')
    if (hasCreating && !prPollRef.current) {
      prPollRef.current = setInterval(async () => {
        try {
          const updated = await getSession(sessionId)
          const latestIter = updated.iterations[updated.iterations.length - 1]
          const stillCreating = latestIter?.proposals.some((p) => p.pr_status === 'creating')
          if (!stillCreating) {
            if (prPollRef.current) {
              clearInterval(prPollRef.current)
              prPollRef.current = null
            }
            refetch()
          }
        } catch {
          // Ignore polling errors
        }
      }, 3000)
    }

    if (!hasCreating && prPollRef.current) {
      clearInterval(prPollRef.current)
      prPollRef.current = null
    }

    return () => {
      if (prPollRef.current) {
        clearInterval(prPollRef.current)
        prPollRef.current = null
      }
    }
  }, [session, sessionId, latestIteration, refetch])

  if (!sessionId) return <p>Invalid session ID</p>

  if (isLoading && !session) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
        <p>Loading...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
        <p style={{ color: '#dc2626' }}>Error: {error}</p>
      </div>
    )
  }

  if (!session) return null

  const iterationStatus = latestIteration?.status ?? 'pending'
  const isInProgress = ['pending', 'analyzing', 'implementing'].includes(iterationStatus)
  const isMobile = latestIteration?.device_type === 'mobile'
  const cardMinWidth = isMobile ? '240px' : '400px'
  const completedProposals =
    latestIteration?.proposals.filter((p) => p.status === 'completed' && p.after_screenshot_url) ??
    []

  const selectedProposal: Proposal | null =
    selectedIndex !== null
      ? (completedProposals.find((p) => p.proposal_index === selectedIndex) ?? null)
      : null

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
      {/* Session header */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ fontSize: '20px', margin: 0 }}>Session Detail</h1>
          <StatusBadge status={iterationStatus} />
        </div>
        <div style={{ fontSize: '16px', color: '#6b7280', marginTop: '8px' }}>
          <div>Repository: {session.repo_url}</div>
          <div>Branch: {session.base_branch}</div>
        </div>
      </div>

      {/* Iteration timeline */}
      {session.iterations.length > 1 && (
        <div style={{ marginBottom: '24px' }}>
          <h2 style={{ fontSize: '16px', marginBottom: '8px', color: '#9ca3af' }}>
            Iterations ({session.iterations.length})
          </h2>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {session.iterations.map((iter, idx) => (
              <div
                key={iter.id}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  backgroundColor: idx === session.iterations.length - 1 ? '#374151' : '#1f2937',
                  border:
                    idx === session.iterations.length - 1
                      ? '1px solid #60a5fa'
                      : '1px solid #374151',
                  color: idx === session.iterations.length - 1 ? '#93c5fd' : '#9ca3af',
                }}
              >
                #{idx + 1}: {iter.instruction.substring(0, 40)}
                {iter.instruction.length > 40 ? '...' : ''}
                {iter.selected_proposal_index !== null && (
                  <span style={{ marginLeft: '6px', color: '#6b7280' }}>
                    (selected #{iter.selected_proposal_index + 1})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Current instruction */}
      {latestIteration && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#1f2937',
            border: '1px solid #374151',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '16px',
            color: 'rgba(255,255,255,0.87)',
          }}
        >
          <span style={{ color: '#9ca3af', fontSize: '13px' }}>
            Instruction (iteration #{latestIteration.iteration_index + 1}):
          </span>
          <div style={{ marginTop: '4px' }}>{latestIteration.instruction}</div>
        </div>
      )}

      {/* Error message */}
      {latestIteration?.error_message && (
        <div
          style={{
            padding: '12px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '6px',
            color: '#991b1b',
            fontSize: '16px',
            marginBottom: '16px',
          }}
        >
          {latestIteration.error_message}
        </div>
      )}

      {/* Progress indicator with log streaming */}
      {(isInProgress || logStreamState.jobs.size > 0) && (
        <LogPanel logState={logStreamState} defaultCollapsed={!isInProgress} />
      )}

      {/* Completed: show proposals */}
      {iterationStatus === 'completed' && latestIteration && (
        <>
          {completedProposals.length > 0 && (
            <div>
              <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>
                Select a design ({completedProposals.length} proposals)
              </h2>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(auto-fill, minmax(${cardMinWidth}, 1fr))`,
                  gap: '16px',
                }}
              >
                {latestIteration.before_screenshot_url && (
                  <div
                    style={{
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      backgroundColor: '#fff',
                    }}
                  >
                    <img
                      src={latestIteration.before_screenshot_url}
                      alt="Before"
                      style={{ width: '100%', display: 'block' }}
                    />
                    <div style={{ padding: '10px 12px' }}>
                      <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111' }}>
                        Before
                      </h3>
                    </div>
                  </div>
                )}
                {completedProposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    selected={selectedIndex === proposal.proposal_index}
                    onToggle={toggleProposal}
                  />
                ))}
              </div>

              {/* Create PR button — always visible, disabled until a proposal is selected */}
              <div style={{ marginTop: '16px' }}>
                {(() => {
                  const sp = selectedProposal
                  if (sp?.pr_url) {
                    return (
                      <a
                        href={sp.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'inline-block',
                          padding: '10px 24px',
                          backgroundColor: '#059669',
                          color: '#fff',
                          borderRadius: '6px',
                          textDecoration: 'none',
                          fontSize: '16px',
                          fontWeight: 600,
                        }}
                      >
                        View PR
                      </a>
                    )
                  }
                  if (sp?.pr_status === 'creating') {
                    return (
                      <div
                        style={{
                          display: 'inline-block',
                          padding: '10px 24px',
                          backgroundColor: '#f0f9ff',
                          borderRadius: '6px',
                          fontSize: '16px',
                          color: '#1e40af',
                        }}
                      >
                        Creating PR...
                      </div>
                    )
                  }
                  const canCreate = !!sp && !sp.pr_status && !sp.pr_url
                  const isFailed = sp?.pr_status === 'failed'
                  return (
                    <>
                      {isFailed && (
                        <p style={{ color: '#dc2626', fontSize: '13px', marginBottom: '8px' }}>
                          PR creation failed
                        </p>
                      )}
                      <button
                        onClick={handleCreatePR}
                        disabled={!canCreate && !isFailed || prLoading}
                        style={{
                          padding: '10px 24px',
                          backgroundColor: (canCreate || isFailed) && !prLoading ? '#3b82f6' : '#4b5563',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: (canCreate || isFailed) && !prLoading ? 'pointer' : 'not-allowed',
                          fontSize: '16px',
                          fontWeight: 600,
                          opacity: (canCreate || isFailed) ? 1 : 0.5,
                        }}
                      >
                        {prLoading ? 'Creating PR...' : isFailed ? 'Retry Create PR' : 'Create PR'}
                      </button>
                    </>
                  )
                })()}

                {prError && (
                  <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '8px' }}>
                    {prError}
                  </p>
                )}
              </div>

              {/* Continue Refining — chat-style input */}
              <div
                style={{
                  marginTop: '24px',
                  border: '1px solid #4b5563',
                  borderRadius: '12px',
                  backgroundColor: '#1a1a1a',
                  padding: '12px 16px',
                }}
              >
                <textarea
                  value={continueInstruction}
                  onChange={(e) => setContinueInstruction(e.target.value)}
                  placeholder="Select a base design, then describe additional changes..."
                  rows={2}
                  style={{
                    width: '100%',
                    padding: 0,
                    border: 'none',
                    outline: 'none',
                    fontSize: '15px',
                    resize: 'none',
                    boxSizing: 'border-box',
                    backgroundColor: 'transparent',
                    color: 'rgba(255,255,255,0.87)',
                    lineHeight: '1.5',
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                  <button
                    onClick={handleContinue}
                    disabled={continueLoading || !continueInstruction.trim() || !selectedProposal}
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '50%',
                      border: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor:
                        continueLoading || !continueInstruction.trim() || !selectedProposal
                          ? 'not-allowed'
                          : 'pointer',
                      backgroundColor:
                        continueLoading || !continueInstruction.trim() || !selectedProposal
                          ? '#4b5563'
                          : '#fff',
                      color:
                        continueLoading || !continueInstruction.trim() || !selectedProposal
                          ? '#9ca3af'
                          : '#111',
                      transition: 'background-color 0.15s',
                    }}
                    aria-label="Send"
                  >
                    {continueLoading ? (
                      <span style={{ fontSize: '14px' }}>...</span>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="19" x2="12" y2="5" />
                        <polyline points="5 12 12 5 19 12" />
                      </svg>
                    )}
                  </button>
                </div>
                {continueError && (
                  <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '8px' }}>
                    {continueError}
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
