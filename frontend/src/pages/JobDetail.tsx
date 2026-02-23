import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useJobPolling } from '../hooks/useJobPolling'
import { createPR, getJob } from '../services/api'
import StatusBadge from '../components/StatusBadge'
import ProposalCard from '../components/ProposalCard'

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const { job, error, isLoading, refetch } = useJobPolling(jobId ?? null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [prLoading, setPrLoading] = useState(false)
  const [prError, setPrError] = useState<string | null>(null)
  const prPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const toggleProposal = useCallback((index: number) => {
    setSelectedIndex((prev) => (prev === index ? null : index))
  }, [])

  const handleCreatePR = useCallback(async () => {
    if (selectedIndex === null || !jobId) return
    setPrLoading(true)
    setPrError(null)
    try {
      await createPR(jobId, selectedIndex)
      refetch()
    } catch (e) {
      setPrError((e as Error).message)
    } finally {
      setPrLoading(false)
    }
  }, [selectedIndex, jobId, refetch])

  // Poll for PR status changes when a proposal is "creating"
  useEffect(() => {
    if (!job || !jobId) return

    const hasCreating = job.proposals.some((p) => p.pr_status === 'creating')
    if (hasCreating && !prPollRef.current) {
      prPollRef.current = setInterval(async () => {
        try {
          const updated = await getJob(jobId)
          const stillCreating = updated.proposals.some((p) => p.pr_status === 'creating')
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
  }, [job, jobId, refetch])

  if (!jobId) return <p>Invalid job ID</p>

  if (isLoading && !job) {
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
        <Link to="/">Back to Dashboard</Link>
      </div>
    )
  }

  if (!job) return null

  const isInProgress = ['pending', 'analyzing', 'implementing'].includes(job.status)
  const completedProposals = job.proposals.filter(
    (p) => p.status === 'completed' && p.after_screenshot_url,
  )

  const selectedProposal =
    selectedIndex !== null
      ? completedProposals.find((p) => p.proposal_index === selectedIndex)
      : null

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
      <Link to="/" style={{ fontSize: '14px', color: '#6b7280', textDecoration: 'none' }}>
        &larr; Back to Dashboard
      </Link>

      <div style={{ marginTop: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ fontSize: '20px', margin: 0 }}>Job Detail</h1>
          <StatusBadge status={job.status} />
        </div>
        <div style={{ fontSize: '14px', color: '#6b7280', marginTop: '8px' }}>
          <div>Repository: {job.repo_url}</div>
          <div>Branch: {job.branch}</div>
          <div style={{ marginTop: '4px' }}>Instruction: {job.instruction}</div>
        </div>
      </div>

      {job.error_message && (
        <div
          style={{
            padding: '12px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '6px',
            color: '#991b1b',
            fontSize: '14px',
            marginBottom: '16px',
          }}
        >
          {job.error_message}
        </div>
      )}

      {isInProgress && (
        <div
          style={{
            padding: '16px',
            backgroundColor: '#f0f9ff',
            borderRadius: '6px',
            marginBottom: '16px',
            textAlign: 'center',
            fontSize: '14px',
            color: '#1e40af',
          }}
        >
          {job.status === 'pending' && 'Job is queued...'}
          {job.status === 'analyzing' && 'Analyzing repository and generating proposals...'}
          {job.status === 'implementing' &&
            'Implementing all proposals... This may take a few minutes.'}
        </div>
      )}

      {job.status === 'completed' && (
        <>
          {job.before_screenshot_url && (
            <div style={{ marginBottom: '24px' }}>
              <h2 style={{ fontSize: '16px', marginBottom: '8px' }}>Before</h2>
              <img
                src={job.before_screenshot_url}
                alt="Before"
                style={{ maxWidth: '100%', borderRadius: '6px', border: '1px solid #e5e7eb' }}
              />
            </div>
          )}

          {completedProposals.length > 0 && (
            <div>
              <h2 style={{ fontSize: '16px', marginBottom: '12px' }}>
                Select a design ({completedProposals.length} proposals)
              </h2>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: '16px',
                }}
              >
                {completedProposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    selected={selectedIndex === proposal.proposal_index}
                    onToggle={toggleProposal}
                  />
                ))}
              </div>

              {selectedProposal && (
                <div style={{ marginTop: '16px', textAlign: 'center' }}>
                  {selectedProposal.pr_url && (
                    <a
                      href={selectedProposal.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '10px 24px',
                        backgroundColor: '#059669',
                        color: '#fff',
                        borderRadius: '6px',
                        textDecoration: 'none',
                        fontSize: '14px',
                        fontWeight: 600,
                      }}
                    >
                      View PR
                    </a>
                  )}
                  {selectedProposal.pr_status === 'creating' && (
                    <div
                      style={{
                        padding: '10px 24px',
                        backgroundColor: '#f0f9ff',
                        borderRadius: '6px',
                        fontSize: '14px',
                        color: '#1e40af',
                      }}
                    >
                      Creating PR...
                    </div>
                  )}
                  {selectedProposal.pr_status === 'failed' && (
                    <div>
                      <p style={{ color: '#dc2626', fontSize: '14px', marginBottom: '8px' }}>
                        PR creation failed
                      </p>
                      <button
                        onClick={handleCreatePR}
                        disabled={prLoading}
                        style={{
                          padding: '10px 24px',
                          backgroundColor: '#3b82f6',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: prLoading ? 'not-allowed' : 'pointer',
                          fontSize: '14px',
                          fontWeight: 600,
                          opacity: prLoading ? 0.7 : 1,
                        }}
                      >
                        {prLoading ? 'Creating PR...' : 'Retry Create PR'}
                      </button>
                    </div>
                  )}
                  {!selectedProposal.pr_status && !selectedProposal.pr_url && (
                    <button
                      onClick={handleCreatePR}
                      disabled={prLoading}
                      style={{
                        padding: '10px 24px',
                        backgroundColor: '#3b82f6',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: prLoading ? 'not-allowed' : 'pointer',
                        fontSize: '14px',
                        fontWeight: 600,
                        opacity: prLoading ? 0.7 : 1,
                      }}
                    >
                      {prLoading ? 'Creating PR...' : 'Create PR'}
                    </button>
                  )}
                  {prError && (
                    <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '8px' }}>
                      {prError}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
