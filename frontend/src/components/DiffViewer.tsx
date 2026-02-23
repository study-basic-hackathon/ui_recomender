type DiffViewerProps = {
  diff: string
  onClose: () => void
}

export default function DiffViewer({ diff, onClose }: DiffViewerProps) {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#1e1e1e',
          borderRadius: '8px',
          padding: '16px',
          maxWidth: '90vw',
          maxHeight: '90vh',
          overflow: 'auto',
          minWidth: '600px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '12px',
          }}
        >
          <h3 style={{ margin: 0, color: '#e5e7eb' }}>Changes Diff</h3>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#9ca3af',
              fontSize: '20px',
              cursor: 'pointer',
            }}
          >
            &times;
          </button>
        </div>
        <pre
          style={{
            margin: 0,
            padding: '12px',
            backgroundColor: '#111827',
            borderRadius: '4px',
            fontSize: '13px',
            lineHeight: 1.5,
            color: '#d1d5db',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {diff.split('\n').map((line, i) => {
            let color = '#d1d5db'
            if (line.startsWith('+') && !line.startsWith('+++')) color = '#34d399'
            else if (line.startsWith('-') && !line.startsWith('---')) color = '#f87171'
            else if (line.startsWith('@@')) color = '#60a5fa'
            return (
              <div key={i} style={{ color }}>
                {line}
              </div>
            )
          })}
        </pre>
      </div>
    </div>
  )
}
