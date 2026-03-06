import type { Proposal } from '../services/api'

type ProposalCardProps = {
  proposal: Proposal
  selected: boolean
  onToggle: (index: number) => void
}

export default function ProposalCard({ proposal, selected, onToggle }: ProposalCardProps) {
  if (proposal.status !== 'completed' || !proposal.after_screenshot_url) {
    return null
  }

  return (
    <div
      style={{
        border: selected ? '3px solid #3b82f6' : '1px solid #e5e7eb',
        borderRadius: '8px',
        overflow: 'hidden',
        cursor: 'pointer',
        backgroundColor: selected ? '#eff6ff' : '#fff',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        boxShadow: selected ? '0 0 0 2px rgba(59,130,246,0.3)' : 'none',
      }}
      onClick={() => onToggle(proposal.proposal_index)}
    >
      <img
        src={proposal.after_screenshot_url}
        alt={proposal.title}
        style={{ width: '100%', display: 'block' }}
      />
      <div style={{ padding: '10px 12px' }}>
        <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#111' }}>
          #{proposal.proposal_index + 1}: {proposal.title}
        </h3>
      </div>
    </div>
  )
}
