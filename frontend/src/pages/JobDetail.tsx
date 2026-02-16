import { useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useJobPolling } from '../hooks/useJobPolling';
import StatusBadge from '../components/StatusBadge';
import ProposalCard from '../components/ProposalCard';

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, error, isLoading } = useJobPolling(jobId ?? null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const toggleProposal = useCallback((index: number) => {
    setSelectedIndex((prev) => (prev === index ? null : index));
  }, []);

  if (!jobId) return <p>Invalid job ID</p>;

  if (isLoading && !job) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
        <p style={{ color: '#dc2626' }}>Error: {error}</p>
        <Link to="/">Back to Dashboard</Link>
      </div>
    );
  }

  if (!job) return null;

  const isInProgress = ['pending', 'analyzing', 'implementing'].includes(job.status);
  const completedProposals = job.proposals.filter(
    (p) => p.status === 'completed' && p.after_screenshot_url,
  );

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
        <div style={{
          padding: '12px',
          backgroundColor: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: '6px',
          color: '#991b1b',
          fontSize: '14px',
          marginBottom: '16px',
        }}>
          {job.error_message}
        </div>
      )}

      {isInProgress && (
        <div style={{
          padding: '16px',
          backgroundColor: '#f0f9ff',
          borderRadius: '6px',
          marginBottom: '16px',
          textAlign: 'center',
          fontSize: '14px',
          color: '#1e40af',
        }}>
          {job.status === 'pending' && 'Job is queued...'}
          {job.status === 'analyzing' && 'Analyzing repository and generating proposals...'}
          {job.status === 'implementing' && 'Implementing all proposals... This may take a few minutes.'}
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
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '16px',
              }}>
                {completedProposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    selected={selectedIndex === proposal.proposal_index}
                    onToggle={toggleProposal}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
