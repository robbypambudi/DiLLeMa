import type { FormEvent } from 'react'

import { Button } from '@/shared/components/ui/Button'
import { Input } from '@/shared/components/ui/Input'

interface RenameDialogProps {
  open: boolean
  title: string
  value: string
  saving?: boolean
  onChange: (value: string) => void
  onCancel: () => void
  onConfirm: () => void
}

export function RenameDialog({
  open,
  title,
  value,
  saving = false,
  onChange,
  onCancel,
  onConfirm,
}: RenameDialogProps) {
  if (!open) return null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!value.trim() || saving) return
    onConfirm()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <form onSubmit={submit} className="surface-card mx-4 w-full max-w-md space-y-5 p-6 shadow-xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        <div className="space-y-2">
          <label className="field-label" htmlFor="rename-collection">Collection name</label>
          <Input
            id="rename-collection"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            autoFocus
            required
          />
        </div>
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving || !value.trim()}>
            {saving ? 'Saving…' : 'Rename'}
          </Button>
        </div>
      </form>
    </div>
  )
}
