const BASE_URL = '/api'

export interface Proposal {
  id: string
  proposal_index: number
  title: string
  concept: string
  plan: string[]
  files: { path: string; reason: string }[]
  complexity: string | null
  status: 'pending' | 'implementing' | 'completed' | 'failed'
  after_screenshot_url: string | null
  diff_key: string | null
  pr_url: string | null
  pr_status: string | null
  error_message: string | null
  created_at: string
}

export interface Iteration {
  id: string
  iteration_index: number
  instruction: string
  selected_proposal_index: number | null
  status: 'pending' | 'analyzing' | 'analyzed' | 'implementing' | 'completed' | 'failed'
  before_screenshot_url: string | null
  error_message: string | null
  proposals: Proposal[]
  created_at: string
}

export interface Session {
  id: string
  repo_url: string
  base_branch: string
  status: 'active' | 'completed' | 'archived'
  iterations: Iteration[]
  created_at: string
  updated_at: string
}

export interface CreateSessionRequest {
  repo_url: string
  branch: string
  instruction: string
}

export interface Setting {
  key: string
  value: string
  updated_at: string
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const error = await res.text()
    throw new Error(`API error (${res.status}): ${error}`)
  }
  return res.json()
}

export async function createSession(data: CreateSessionRequest): Promise<Session> {
  const res = await fetch(`${BASE_URL}/sessions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return handleResponse<Session>(res)
}

export async function listSessions(): Promise<Session[]> {
  const res = await fetch(`${BASE_URL}/sessions/`)
  return handleResponse<Session[]>(res)
}

export async function getSession(id: string): Promise<Session> {
  const res = await fetch(`${BASE_URL}/sessions/${id}`)
  return handleResponse<Session>(res)
}

export async function iterate(
  sessionId: string,
  selectedProposalIndex: number,
  instruction: string,
): Promise<Session> {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/iterate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_proposal_index: selectedProposalIndex,
      instruction,
    }),
  })
  return handleResponse<Session>(res)
}

export async function createPR(
  sessionId: string,
  iterationIndex: number,
  proposalIndex: number,
): Promise<Proposal> {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/create-pr`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      iteration_index: iterationIndex,
      proposal_index: proposalIndex,
    }),
  })
  return handleResponse<Proposal>(res)
}

export async function getDiff(
  sessionId: string,
  iterationIndex: number,
  proposalIndex: number,
): Promise<string> {
  const res = await fetch(
    `${BASE_URL}/sessions/${sessionId}/iterations/${iterationIndex}/proposals/${proposalIndex}/diff`,
  )
  const data = await handleResponse<{ diff: string }>(res)
  return data.diff
}

export async function getSettings(): Promise<Setting[]> {
  const res = await fetch(`${BASE_URL}/settings/`)
  return handleResponse<Setting[]>(res)
}

export async function saveSetting(key: string, value: string): Promise<Setting> {
  const res = await fetch(`${BASE_URL}/settings/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  })
  return handleResponse<Setting>(res)
}
