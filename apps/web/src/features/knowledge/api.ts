import { apiRequest } from '@/shared/api/client'
import type { Claim, ClaimStatus, Job, KnowledgeProfile, ProfileResponse } from './types'

const base = (id: string) => `/api/v1/knowledge/${encodeURIComponent(id)}`

export const knowledgeApi = {
  profile: (id: string, signal?: AbortSignal) => apiRequest<ProfileResponse>(`${base(id)}/profile`, { signal }),
  saveProfile: (id: string, profile: KnowledgeProfile) => apiRequest<ProfileResponse>(`${base(id)}/profile`, { method: 'PUT', body: JSON.stringify(profile) }),
  jobs: (id: string, signal?: AbortSignal) => apiRequest<{ data: Job[] }>(`${base(id)}/jobs`, { signal }),
  claims: (id: string, status: ClaimStatus, offset: number, signal?: AbortSignal) => apiRequest<{ data: Claim[] }>(`${base(id)}/claims?${new URLSearchParams({ status, offset: String(offset), limit: '20' })}`, { signal }),
  extract: (id: string, fileId: string) => apiRequest<{ id: string; status: string }>(`${base(id)}/files/${encodeURIComponent(fileId)}/extract`, { method: 'POST' }),
  review: (id: string, claimId: string, status: Exclude<ClaimStatus, 'pending'>) => apiRequest<{ id: string; status: ClaimStatus }>(`${base(id)}/claims/${encodeURIComponent(claimId)}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
}
