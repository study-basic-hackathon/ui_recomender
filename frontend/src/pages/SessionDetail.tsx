import { useState, useCallback, useEffect, useRef, Fragment } from 'react'
import { useParams } from 'react-router-dom'
import { useSessionPolling } from '../hooks/useSessionPolling'
import { useLogStream } from '../hooks/useLogStream'
import { createPR, iterate, getSession } from '../services/api'
import type { Iteration, Proposal } from '../services/api'
import { useLayoutContext } from '../hooks/useLayoutContext'
import StatusBadge from '../components/StatusBadge'
import ProposalCard from '../components/ProposalCard'
import LogPanel from '../components/LogPanel'
import type { LogStreamState } from '../hooks/useLogStream'

function extractRepoName(repoUrl: string): string {
  try {
    const parts = repoUrl.replace(/\.git$/, '').split('/')
    return parts.slice(-2).join('/')
  } catch {
    return repoUrl
  }
}

/* ------------------------------------------------------------------ */
/*  IterationBlock — renders a single iteration in the chat stack     */
/* ------------------------------------------------------------------ */

type IterationBlockProps = {
  iteration: Iteration
  isLatest: boolean
  // latest-only interactive props
  selectedIndex: number | null
  onToggleProposal: (index: number) => void
  onCreatePR: () => void
  prLoading: boolean
  prError: string | null
  // log stream
  logStreamState: LogStreamState
  isInProgress: boolean
}

function IterationBlock({
  iteration,
  isLatest,
  selectedIndex,
  onToggleProposal,
  onCreatePR,
  prLoading,
  prError,
  logStreamState,
  isInProgress,
}: IterationBlockProps) {
  const isMobile = iteration.device_type === 'mobile'
  const cardMinWidth = isMobile ? '240px' : '400px'
  const completedProposals = iteration.proposals.filter(
    (p) => p.status === 'completed' && p.after_screenshot_url,
  )

  // For past iterations, highlight the selected proposal; for latest, use interactive selection
  const effectiveSelectedIndex = isLatest
    ? selectedIndex
    : iteration.selected_proposal_index

  const selectedProposal: Proposal | null =
    effectiveSelectedIndex !== null
      ? (completedProposals.find((p) => p.proposal_index === effectiveSelectedIndex) ?? null)
      : null

  return (
    <div>
      {/* Instruction bubble — chat-style, right-aligned */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '16px' }}>
        <div
          style={{
            maxWidth: '80%',
            padding: '10px 18px',
            backgroundColor: '#374151',
            borderRadius: '20px',
            fontSize: '15px',
            color: 'rgba(255,255,255,0.87)',
            lineHeight: '1.5',
          }}
        >
          {iteration.instruction}
        </div>
      </div>

      {/* Error message */}
      {iteration.error_message && (
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
          {iteration.error_message}
        </div>
      )}

      {/* Log panel — live when latest & in-progress, collapsed otherwise */}
      {isLatest && (isInProgress || logStreamState.jobs.size > 0) && (
        <LogPanel logState={logStreamState} defaultCollapsed={!isInProgress} />
      )}

      {/* Proposals grid */}
      {iteration.status === 'completed' && completedProposals.length > 0 && (
        <div>
          <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>
            {isLatest
              ? `Select a design (${completedProposals.length} proposals)`
              : `Proposals (${completedProposals.length})`}
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(auto-fill, minmax(${cardMinWidth}, 1fr))`,
              gap: '16px',
            }}
          >
            {iteration.before_screenshot_url && (
              <div
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  backgroundColor: '#fff',
                }}
              >
                <img
                  src={iteration.before_screenshot_url}
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
                selected={effectiveSelectedIndex === proposal.proposal_index}
                onToggle={onToggleProposal}
                readOnly={!isLatest}
              />
            ))}
          </div>

          {/* Create PR button — latest only */}
          {isLatest && (
            <>
              {/* Create PR button */}
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
                        onClick={onCreatePR}
                        disabled={(!canCreate && !isFailed) || prLoading}
                        style={{
                          padding: '10px 24px',
                          backgroundColor:
                            (canCreate || isFailed) && !prLoading ? '#3b82f6' : '#4b5563',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          cursor:
                            (canCreate || isFailed) && !prLoading ? 'pointer' : 'not-allowed',
                          fontSize: '16px',
                          fontWeight: 600,
                          opacity: canCreate || isFailed ? 1 : 0.5,
                        }}
                      >
                        {prLoading
                          ? 'Creating PR...'
                          : isFailed
                            ? 'Retry Create PR'
                            : 'Create PR'}
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

            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  SessionDetail — main component                                     */
/* ------------------------------------------------------------------ */

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const { refreshSessions, setHeaderExtra } = useLayoutContext()
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
  const bottomRef = useRef<HTMLDivElement>(null)

  // Reset selection when session changes
  useEffect(() => {
    setSelectedIndex(null)
    setContinueInstruction('')
  }, [sessionId])

  // Auto-scroll when new iterations are added
  const iterationCount = session?.iterations.length ?? 0
  useEffect(() => {
    if (iterationCount > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [iterationCount])

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

  // Push repo/branch/badge into the Layout header
  const iterationStatus = latestIteration?.status ?? 'pending'
  useEffect(() => {
    if (session) {
      setHeaderExtra(
        <>
          <div className="header-repo-info" style={{ display: 'flex', gap: '16px', alignItems: 'center', fontSize: '16px', color: '#6b7280' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
              {extractRepoName(session.repo_url)}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path fillRule="evenodd" d="M11.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122V6A2.5 2.5 0 0110 8.5H6a1 1 0 00-1 1v1.128a2.251 2.251 0 11-1.5 0V5.372a2.25 2.25 0 111.5 0v1.836A2.492 2.492 0 016 7h4a1 1 0 001-1v-.628A2.25 2.25 0 019.5 3.25zM4.25 12a.75.75 0 100 1.5.75.75 0 000-1.5zM3.5 3.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0z" />
              </svg>
              {session.base_branch}
            </span>
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <StatusBadge status={iterationStatus} />
          </div>
        </>
      )
    }
    return () => setHeaderExtra(null)
  }, [session, iterationStatus, setHeaderExtra])

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

  const isInProgress = ['pending', 'analyzing', 'implementing'].includes(iterationStatus)

  const completedProposalsForInput = latestIteration?.proposals.filter(
    (p) => p.status === 'completed' && p.after_screenshot_url,
  ) ?? []
  const selectedProposal = selectedIndex !== null
    ? (completedProposalsForInput.find((p) => p.proposal_index === selectedIndex) ?? null)
    : null
  const showContinueInput = latestIteration?.status === 'completed' && completedProposalsForInput.length > 0

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '0px 24px 12px' }}>
      {/* All iterations stacked */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', overflow: 'hidden' }}>
        {session.iterations.map((iter, idx) => (
          <Fragment key={iter.id}>
            {idx > 0 && (
              <hr
                style={{
                  border: 'none',
                  borderTop: '1px solid #374151',
                  margin: 0,
                }}
              />
            )}
            <IterationBlock
              iteration={iter}
              isLatest={idx === session.iterations.length - 1}
              selectedIndex={selectedIndex}
              onToggleProposal={toggleProposal}
              onCreatePR={handleCreatePR}
              prLoading={prLoading}
              prError={prError}
              logStreamState={logStreamState}
              isInProgress={isInProgress}
            />
          </Fragment>
        ))}
      </div>

      {/* Sticky input bar */}
      {showContinueInput && (
        <div
          style={{
            position: 'sticky',
            bottom: 0,
            backgroundColor: '#242424',
            paddingTop: '16px',
            paddingBottom: '12px',
            zIndex: 10,
          }}
        >
          <div
            style={{
              border: '1px solid #4b5563',
              borderRadius: '12px',
              backgroundColor: '#1a1a1a',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'flex-end',
              gap: '8px',
            }}
          >
            <textarea
              value={continueInstruction}
              onChange={(e) => setContinueInstruction(e.target.value)}
              placeholder="Select a base design, then describe additional changes..."
              rows={3}
              style={{
                flex: 1,
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
            <button
              onClick={handleContinue}
              disabled={continueLoading || !continueInstruction.trim() || !selectedProposal}
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                border: 'none',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor:
                  continueLoading || !continueInstruction.trim() || !selectedProposal
                    ? 'not-allowed'
                    : 'pointer',
                backgroundColor:
                  continueLoading || !continueInstruction.trim() || !selectedProposal
                    ? 'rgba(255,255,255,0.15)'
                    : '#fff',
                color: '#111',
                transition: 'background-color 0.15s',
              }}
              aria-label="Send"
            >
              {continueLoading ? (
                <span style={{ fontSize: '14px' }}>...</span>
              ) : (
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  style={{ display: 'block', flexShrink: 0 }}
                >
                  <path
                    d="M12 19V5M12 5l-7 7M12 5l7 7"
                    fill="none"
                    stroke={
                      continueLoading || !continueInstruction.trim() || !selectedProposal
                        ? 'rgba(255,255,255,0.5)'
                        : '#000000'
                    }
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
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
      )}

      {/* Auto-scroll anchor */}
      <div ref={bottomRef} />
    </div>
  )
}
