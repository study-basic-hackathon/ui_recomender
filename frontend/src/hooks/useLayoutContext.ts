import { useOutletContext } from 'react-router-dom'
import type { ReactNode } from 'react'

type LayoutContext = {
  refreshSessions: () => void
  setHeaderExtra: (content: ReactNode | null) => void
}

export function useLayoutContext() {
  return useOutletContext<LayoutContext>()
}
