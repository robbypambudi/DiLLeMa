import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '@/shared/lib/errors'
import { collectionsApi } from '../api'
import type { Collection } from '../types'

export function useCollectionList() {
  const [rows, setRows] = useState<Collection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)
  const load = useCallback(async () => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const body = await collectionsApi.list(controller.signal)
      if (!controller.signal.aborted) setRows(body.data || [])
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    return () => request.current?.abort()
  }, [load])

  return { rows, loading, error, setError, load }
}
