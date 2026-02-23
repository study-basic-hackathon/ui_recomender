import { useOutletContext } from 'react-router-dom'

type LayoutContext = {
  refreshJobs: () => void
}

export function useLayoutContext() {
  return useOutletContext<LayoutContext>()
}
