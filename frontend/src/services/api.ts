const BASE_URL = '/api';

export interface Proposal {
  id: string;
  proposal_index: number;
  title: string;
  concept: string;
  plan: string[];
  files: { path: string; reason: string }[];
  complexity: string | null;
  status: 'pending' | 'implementing' | 'completed' | 'failed';
  after_screenshot_url: string | null;
  error_message: string | null;
  created_at: string;
}

export interface Job {
  id: string;
  status: 'pending' | 'analyzing' | 'analyzed' | 'implementing' | 'completed' | 'failed';
  repo_url: string;
  branch: string;
  instruction: string;
  before_screenshot_url: string | null;
  error_message: string | null;
  proposals: Proposal[];
  created_at: string;
  updated_at: string;
}

export interface CreateJobRequest {
  repo_url: string;
  branch: string;
  instruction: string;
}

export interface Setting {
  key: string;
  value: string;
  updated_at: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error (${res.status}): ${error}`);
  }
  return res.json();
}

export async function createJob(data: CreateJobRequest): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Job>(res);
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch(`${BASE_URL}/jobs/`);
  return handleResponse<Job[]>(res);
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/${id}`);
  return handleResponse<Job>(res);
}

export async function implementProposals(
  jobId: string,
  proposalIndices: number[],
): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/implement`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proposal_indices: proposalIndices }),
  });
  return handleResponse<Job>(res);
}

export async function getDiff(
  jobId: string,
  proposalIndex: number,
): Promise<string> {
  const res = await fetch(
    `${BASE_URL}/jobs/${jobId}/proposals/${proposalIndex}/diff`,
  );
  const data = await handleResponse<{ diff: string }>(res);
  return data.diff;
}

export async function getSettings(): Promise<Setting[]> {
  const res = await fetch(`${BASE_URL}/settings/`);
  return handleResponse<Setting[]>(res);
}

export async function saveSetting(key: string, value: string): Promise<Setting> {
  const res = await fetch(`${BASE_URL}/settings/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  });
  return handleResponse<Setting>(res);
}
