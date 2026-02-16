type ScreenshotComparisonProps = {
  beforeUrl: string | null;
  afterUrl: string | null;
};

export default function ScreenshotComparison({
  beforeUrl,
  afterUrl,
}: ScreenshotComparisonProps) {
  if (!beforeUrl && !afterUrl) return null;

  return (
    <div style={{ display: 'flex', gap: '16px', marginTop: '16px', flexWrap: 'wrap' }}>
      {beforeUrl && (
        <div style={{ flex: 1, minWidth: '300px' }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#6b7280' }}>Before</h4>
          <img
            src={beforeUrl}
            alt="Before"
            style={{
              maxWidth: '100%',
              borderRadius: '4px',
              border: '1px solid #e5e7eb',
            }}
          />
        </div>
      )}
      {afterUrl && (
        <div style={{ flex: 1, minWidth: '300px' }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#6b7280' }}>After</h4>
          <img
            src={afterUrl}
            alt="After"
            style={{
              maxWidth: '100%',
              borderRadius: '4px',
              border: '1px solid #e5e7eb',
            }}
          />
        </div>
      )}
    </div>
  );
}
