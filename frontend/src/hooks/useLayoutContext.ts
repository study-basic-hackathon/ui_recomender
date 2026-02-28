import { useOutletContext } from 'react-router-dom'

type LayoutContext = {
  refreshSessions: () => void
}

export function useLayoutContext() {
  return useOutletContext<LayoutContext>()
}
