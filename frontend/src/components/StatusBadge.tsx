type StatusBadgeProps = {
  status: string
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: '#e5e7eb', text: '#374151', label: 'Pending' },
  analyzing: { bg: '#dbeafe', text: '#1d4ed8', label: 'Analyzing' },
  analyzed: { bg: '#d1fae5', text: '#065f46', label: 'Ready' },
  implementing: { bg: '#fef3c7', text: '#92400e', label: 'Implementing' },
  completed: { bg: '#d1fae5', text: '#065f46', label: 'Completed' },
  failed: { bg: '#fee2e2', text: '#991b1b', label: 'Failed' },
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '4px 12px',
        borderRadius: '12px',
        fontSize: '14px',
        fontWeight: 600,
        backgroundColor: style.bg,
        color: style.text,
      }}
    >
      {style.label}
    </span>
  )
}
