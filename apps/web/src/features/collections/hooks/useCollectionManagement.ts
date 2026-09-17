import { useMemo, useState } from 'react'
import { errorMessage } from '@/shared/lib/errors'
import { collectionsApi } from '../api'
import type { Collection } from '../types'
import { useCollectionList } from './useCollectionList'

export function useCollectionManagement() {
  const { rows, loading, error, setError, load } = useCollectionList()
  const [filter, setFilter] = useState('')
  const [pendingDelete, setPendingDelete] = useState<Collection | null>(null)
  const [pendingRename, setPendingRename] = useState<Collection | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((row) => row.collection_name.toLowerCase().includes(q))
  }, [rows, filter])

  const confirmDelete = async () => {
    if (!pendingDelete || deleting) return
    setDeleting(true)
    setError('')
    try {
      await collectionsApi.remove(pendingDelete.id)
      setPendingDelete(null)
      await load()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setDeleting(false)
    }
  }

  const confirmRename = async () => {
    if (!pendingRename || renaming) return
    const nextName = renameValue.trim()
    if (!nextName) return
    setRenaming(true)
    setError('')
    try {
      await collectionsApi.update(pendingRename.id, { collection_name: nextName })
      setPendingRename(null)
      await load()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setRenaming(false)
    }
  }

  return { rows, filter, setFilter, error, loading, pendingDelete, setPendingDelete,
    pendingRename, setPendingRename, renameValue, setRenameValue, renaming, deleting,
    visible, confirmDelete, confirmRename }
}
