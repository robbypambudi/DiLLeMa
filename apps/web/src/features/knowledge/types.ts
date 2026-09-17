export type ClaimStatus = 'pending' | 'approved' | 'rejected'

export interface KnowledgeProfile {
  enabled: boolean
  entity_types: string[]
  relations: { name: string; subject_types: string[]; object_types: string[]; description: string }[]
  merge_by_name: string[]
  instructions: string
}

export interface ProfileResponse {
  available?: boolean
  revision?: string
  profile: KnowledgeProfile
}

export interface Job {
  id: string
  file_name: string
  status: string
  error?: string | null
}

export interface Claim {
  id: string
  subject_name: string
  object_name: string
  predicate: string
  statement: string
  quote: string
  text: string
  file_name: string
  page?: number | null
  qualifiers: Record<string, string | boolean | null>
}
