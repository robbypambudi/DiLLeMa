import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '@/shared/lib/errors'
import { useCollectionFiles } from '@/features/files/hooks/useCollectionFiles'
import { collectionsApi } from '../api'
import type { Collection } from '../types'

export function useCollectionDetail(id: string | undefined) {
  const navigate = useNavigate()
  const [collection, setCollection] = useState<Collection | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const mounted = useRef(false)
  const request = useRef<AbortController | null>(null)
  const documents = useCollectionFiles(id)

  const load = useCallback(async () => {
    if (!id || !mounted.current) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setError('')
    try {
      const body = await collectionsApi.get(id, controller.signal)
      if (controller.signal.aborted) return
      setCollection(body.data)
      setName(body.data.collection_name)
      setDescription(body.data.description || '')
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    }
  }, [id])

  useEffect(() => {
    mounted.current = true
    setCollection(null)
    void load()
    return () => {
      mounted.current = false
      request.current?.abort()
    }
  }, [load])

  const saveMeta = async (event: FormEvent) => {
    event.preventDefault()
    if (!id || saving || !name.trim()) return
    setSaving(true)
    setError('')
    try {
      await collectionsApi.update(id, { collection_name: name.trim(), description })
      await load()
    } catch (error) { setError(errorMessage(error)) }
    finally { setSaving(false) }
  }

  const confirmDeleteCollection = async () => {
    if (!id || deleting) return
    setDeleting(true)
    setError('')
    try {
      await collectionsApi.remove(id)
      if (mounted.current) navigate('/admin', { replace: true })
    } catch (error) { setError(errorMessage(error)) }
    finally { setDeleting(false) }
  }

  return { ...documents, collection, name, setName, description, setDescription,
    error: error || documents.error, saving, pendingDelete, setPendingDelete, deleting,
    saveMeta, confirmDeleteCollection }
}
