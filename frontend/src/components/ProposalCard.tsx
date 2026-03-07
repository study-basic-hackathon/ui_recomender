import type { Proposal } from '../services/api'

type ProposalCardProps = {
  proposal: Proposal
  selected: boolean
  onToggle: (index: number) => void
  readOnly?: boolean
}

export default function ProposalCard({
  proposal,
  selected,
  onToggle,
  readOnly,
}: ProposalCardProps) {
  if (proposal.status !== 'completed' || !proposal.after_screenshot_url) {
    return null
  }

  const borderColor = readOnly && selected ? '#34d399' : selected ? '#3b82f6' : '#e5e7eb'
  const borderWidth = selected ? '3px' : '1px'
  const bgColor = readOnly && selected ? '#ecfdf5' : selected ? '#eff6ff' : '#fff'
  const shadow =
    readOnly && selected
      ? '0 0 0 2px rgba(52,211,153,0.3)'
      : selected
        ? '0 0 0 2px rgba(59,130,246,0.3)'
        : 'none'

  return (
    <div
      style={{
        border: `${borderWidth} solid ${borderColor}`,
        borderRadius: '8px',
        overflow: 'hidden',
        cursor: readOnly ? 'default' : 'pointer',
        backgroundColor: bgColor,
        transition: 'border-color 0.15s, box-shadow 0.15s',
        boxShadow: shadow,
      }}
      onClick={readOnly ? undefined : () => onToggle(proposal.proposal_index)}
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
