import { useState } from 'react'
import { History, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/shared/components/ui/Button'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { useChat } from '../hooks/useChat'
import type { ConversationSummary } from '../types'

export function ChatHistory() {
  const { state, history, historyLoading, historyError, deletingId, hasMore, isGuest,
    newChat, openConversation, deleteConversation, refreshHistory, loadMore } = useChat()
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null)
  const disabled = state.isLoading || state.isRestoring || !!deletingId

  return (
    <section className="mt-4 min-h-0 border-t pt-4" aria-label="Chat history">
      <Button className="w-full" variant="outline" disabled={disabled} onClick={() => newChat()}>
        <Plus className="h-4 w-4" /> New chat
      </Button>
      <details open className="mt-4">
        <summary className="cursor-pointer text-sm font-semibold">
          <History className="mr-2 inline h-4 w-4" /> Chat history
        </summary>
        <p className="my-2 text-xs text-muted-foreground">{isGuest ? 'Saved in this browser. Sign in to keep new chats in your account.' : 'Saved to your account.'}</p>
        {historyError && <div role="alert" className="my-2 text-xs text-destructive">
          <p>{historyError}</p>
          <Button variant="ghost" size="sm" onClick={refreshHistory} disabled={historyLoading}>
            <RefreshCw className="h-3 w-3" /> Retry
          </Button>
        </div>}
        {historyLoading && <p role="status" className="flex items-center gap-2 py-2 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Loading history…</p>}
        {!historyLoading && !history.length && <p className="py-3 text-xs text-muted-foreground">Your conversations will appear here.</p>}
        <ul className="max-h-36 space-y-1 overflow-y-auto md:max-h-[35vh]">
          {history.map((conversation) => <li key={conversation.id} className={`flex items-center rounded-lg border ${state.conversationId === conversation.id ? 'border-primary/40 bg-primary/10' : 'border-transparent'}`}>
            <button type="button" className="min-w-0 flex-1 rounded-lg px-2 py-2 text-left hover:bg-primary/5 disabled:opacity-50"
              aria-current={state.conversationId === conversation.id ? 'true' : undefined}
              disabled={disabled} onClick={() => { void openConversation(conversation.id) }}>
              <span className="block truncate text-sm font-medium" title={conversation.title}>{conversation.title}</span>
              <span className="block truncate text-xs text-muted-foreground">{conversation.collection_name} · {new Date(conversation.updated_at).toLocaleDateString()}</span>
            </button>
            <Button variant="ghost" size="sm" className="shrink-0 px-2" aria-label={`Delete chat: ${conversation.title}`} disabled={disabled} onClick={() => setPendingDelete(conversation)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </li>)}
        </ul>
        {hasMore && <Button variant="ghost" size="sm" className="mt-2 w-full" disabled={historyLoading || disabled} onClick={loadMore}>Load more</Button>}
      </details>
      <ConfirmDialog open={!!pendingDelete} title="Delete chat" body={`Delete “${pendingDelete?.title}” and its messages? This cannot be undone.`}
        onCancel={() => { if (!deletingId) setPendingDelete(null) }}
        onConfirm={() => {
          if (!pendingDelete || deletingId) return
          void deleteConversation(pendingDelete.id).then(() => setPendingDelete(null))
        }} />
    </section>
  )
}
