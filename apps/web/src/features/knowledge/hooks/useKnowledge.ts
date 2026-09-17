import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '@/shared/lib/errors'
import { knowledgeApi } from '../api'
import type { Claim, ClaimStatus, Job, KnowledgeProfile } from '../types'

export function useKnowledge(collectionId: string) {
  const [available, setAvailable] = useState(false)
  const [profile, setProfile] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [jobs, setJobs] = useState<Job[]>([])
  const [claims, setClaims] = useState<Claim[]>([])
  const [status, setStatus] = useState<ClaimStatus>('pending')
  const [offset, setOffset] = useState(0)
  const [fileId, setFileId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [revision, setRevision] = useState(0)
  const mutation = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoaded(false)
    setAvailable(false)
    setFileId('')
    setOffset(0)
    setJobs([])
    setClaims([])
    setError('')
    knowledgeApi.profile(collectionId, controller.signal).then((body) => {
      if (controller.signal.aborted) return
      setAvailable(Boolean(body.available))
      setEnabled(body.profile.enabled)
      setProfile(JSON.stringify(body.profile, null, 2))
    }).catch((error) => {
      if (!controller.signal.aborted) setError(errorMessage(error))
    }).finally(() => {
      if (!controller.signal.aborted) setLoaded(true)
    })
    return () => controller.abort()
  }, [collectionId])

  useEffect(() => {
    if (!available || !loaded) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const [jobBody, claimBody] = await Promise.all([
          knowledgeApi.jobs(collectionId, controller.signal),
          knowledgeApi.claims(collectionId, status, offset, controller.signal),
        ])
        if (!controller.signal.aborted) { setJobs(jobBody.data); setClaims(claimBody.data) }
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => { void load() }, 5000)
      }
    }
    void load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [available, loaded, collectionId, offset, status, revision])

  const action = useCallback(async (task: () => Promise<unknown>) => {
    if (mutation.current) return
    mutation.current = true
    setBusy(true)
    setError('')
    try { await task(); setRevision((value) => value + 1) }
    catch (error) { setError(errorMessage(error)) }
    finally { mutation.current = false; setBusy(false) }
  }, [])

  const save = () => action(async () => {
    const parsed: unknown = JSON.parse(profile)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new Error('Extraction schema must be a JSON object.')
    }
    // The server validates the schema and its relationship constraints.
    const body = await knowledgeApi.saveProfile(collectionId, { ...parsed, enabled } as KnowledgeProfile)
    setProfile(JSON.stringify(body.profile, null, 2))
    setClaims([])
    setOffset(0)
  })
  const extract = () => action(() => knowledgeApi.extract(collectionId, fileId))
  const review = (claimId: string, nextStatus: Exclude<ClaimStatus, 'pending'>) => action(() => knowledgeApi.review(collectionId, claimId, nextStatus))

  return { available, profile, setProfile, enabled, setEnabled, jobs, claims, status,
    setStatus, offset, setOffset, fileId, setFileId, busy, error, loaded, save, extract, review }
}
