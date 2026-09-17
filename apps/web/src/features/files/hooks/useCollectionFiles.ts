import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '@/shared/lib/errors'
import { filesApi } from '../api'
import type { DocumentFile } from '../types'

export function useCollectionFiles(collectionId: string | undefined) {
  const [files, setFiles] = useState<DocumentFile[]>([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [pendingFile, setPendingFile] = useState<DocumentFile | null>(null)
  const [pollCycle, setPollCycle] = useState(0)
  const mounted = useRef(false)
  const mutation = useRef(false)
  const request = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    if (!collectionId || !mounted.current) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    try {
      const body = await filesApi.list(collectionId, controller.signal)
      if (!controller.signal.aborted) {
        setFiles((body.data || []).filter((file) => !['deleted', 'archived'].includes(file.status)))
      }
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      if (!controller.signal.aborted) setPollCycle((value) => value + 1)
    }
  }, [collectionId])

  useEffect(() => {
    mounted.current = true
    setFiles([])
    setPendingFile(null)
    setError('')
    void load()
    return () => {
      mounted.current = false
      request.current?.abort()
    }
  }, [load])

  useEffect(() => {
    if (!files.some((file) => ['pending', 'processing'].includes(file.status))) return
    // A new timer is scheduled only after the previous result has arrived.
    const timer = window.setTimeout(() => { void load() }, 2000)
    return () => window.clearTimeout(timer)
  }, [files, load, pollCycle])

  const action = async (task: () => Promise<void>) => {
    if (mutation.current) return
    mutation.current = true
    setError('')
    try { await task() }
    catch (error) { if (mounted.current) setError(errorMessage(error)) }
    finally {
      await load()
      mutation.current = false
    }
  }

  const uploadFiles = async (fileList: FileList | null) => {
    if (!collectionId || !fileList?.length || mutation.current) return
    const selected = Array.from(fileList)
    setUploading(true)
    try {
      await action(async () => {
        for (const file of selected) {
          if (!mounted.current) break
          await filesApi.upload(collectionId, file)
        }
      })
    } finally { setUploading(false) }
  }

  const retry = (file: DocumentFile) => action(async () => { await filesApi.retry(file.id) })
  const confirmDeleteFile = () => action(async () => {
    if (!pendingFile) return
    await filesApi.remove(pendingFile.id)
    setPendingFile(null)
  })

  return { files, error, uploading, pendingFile, setPendingFile, uploadFiles, retry, confirmDeleteFile }
}
