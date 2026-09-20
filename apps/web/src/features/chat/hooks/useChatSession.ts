import { useCallback, useEffect, useRef, useState } from 'react'
import type { Collection } from '@/features/collections/types'
import { errorMessage } from '@/shared/lib/errors'
import { conversationsApi, streamAnswer } from '../api'
import { conversationCollection, conversationTitle, fromResponse } from '../lib/history'
import { readActiveConversation, readGuestHistory, writeActiveConversation, writeGuestHistory } from '../lib/historyStorage'
import type { ChatState, Conversation, ConversationSummary, Message, SourceRef, ThinkingStep } from '../types'

const initialState: ChatState = {
  selectedCollection: null, conversationId: null, messages: [],
  isLoading: false, isRestoring: false,
}

export function useChatSession(userId: string | null, ready: boolean) {
  const [state, setState] = useState<ChatState>(initialState)
  const stateRef = useRef(state)
  const [history, setHistory] = useState<ConversationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const guestHistory = useRef<Conversation[]>([])
  const guestStorageReady = useRef(false)
  const mounted = useRef(false)
  const stream = useRef<AbortController | null>(null)
  const detailRequest = useRef<AbortController | null>(null)
  const listRequest = useRef<AbortController | null>(null)

  const patchState = useCallback((updates: Partial<ChatState>) => {
    if (!mounted.current) return
    stateRef.current = { ...stateRef.current, ...updates }
    setState(stateRef.current)
  }, [])

  const rememberActive = useCallback((id: string | null) => {
    try { writeActiveConversation(userId, id) }
    catch { setHistoryError('The active chat could not be remembered in this browser.') }
  }, [userId])

  const refreshHistory = useCallback(async (offset = 0) => {
    if (!userId) {
      if (!guestStorageReady.current) {
        try {
          const saved = readGuestHistory()
          guestHistory.current = [...guestHistory.current, ...saved.filter((item) => !guestHistory.current.some((current) => current.id === item.id))]
          guestStorageReady.current = true
        } catch (error) {
          setHistoryError(errorMessage(error))
          return
        }
      }
      setHistory([...guestHistory.current])
      setTotal(guestHistory.current.length)
      return
    }
    listRequest.current?.abort()
    const controller = new AbortController()
    listRequest.current = controller
    setHistoryLoading(true)
    try {
      const body = await conversationsApi.list(offset, controller.signal)
      if (!mounted.current || controller.signal.aborted) return
      setHistory((previous) => offset ? [...previous, ...body.data.filter((row) => !previous.some((item) => item.id === row.id))] : body.data)
      setTotal(body.total)
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) setHistoryError(errorMessage(error))
    } finally {
      if (!controller.signal.aborted && mounted.current) setHistoryLoading(false)
    }
  }, [userId])

  const openConversation = useCallback(async (id: string, quiet = false) => {
    if (stream.current) return
    detailRequest.current?.abort()
    const controller = new AbortController()
    detailRequest.current = controller
    if (!quiet) patchState({ isRestoring: true })
    setHistoryError('')
    try {
      const conversation = userId
        ? fromResponse((await conversationsApi.get(id, controller.signal)).data)
        : guestHistory.current.find((item) => item.id === id)
      if (!mounted.current || controller.signal.aborted) return
      if (!conversation) throw new Error('This conversation is no longer available.')
      patchState({
        conversationId: id, selectedCollection: conversationCollection(conversation),
        messages: conversation.messages, isRestoring: false,
      })
      rememberActive(id)
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) {
        setHistoryError(errorMessage(error))
        patchState({ isRestoring: false })
      }
    }
  }, [userId, patchState, rememberActive])

  useEffect(() => {
    mounted.current = true
    if (ready) {
      try {
        if (!userId) {
          guestHistory.current = readGuestHistory()
          guestStorageReady.current = true
        }
        void refreshHistory()
        const activeId = readActiveConversation(userId)
        if (activeId) void openConversation(activeId)
      } catch (error) { setHistoryError(errorMessage(error)) }
    }
    return () => {
      mounted.current = false
      stream.current?.abort()
      detailRequest.current?.abort()
      listRequest.current?.abort()
    }
  }, [ready, userId, openConversation, refreshHistory])

  // Reopening a chat generated in another tab/device shows its saved completion.
  const hasPendingTurn = state.messages.some((message) => message.status === 'pending')
  useEffect(() => {
    if (!userId || !state.conversationId || state.isLoading || state.isRestoring || !hasPendingTurn) return
    const id = state.conversationId
    let stopped = false
    let timer: number
    const poll = async () => {
      await openConversation(id, true)
      if (!stopped) timer = window.setTimeout(() => { void poll() }, 2500)
    }
    timer = window.setTimeout(() => { void poll() }, 2500)
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [userId, state.conversationId, state.isLoading, state.isRestoring, hasPendingTurn, openConversation])

  const newChat = useCallback((collection?: Collection) => {
    if (stream.current) return
    detailRequest.current?.abort()
    patchState({ ...initialState, selectedCollection: collection ?? stateRef.current.selectedCollection })
    rememberActive(null)
  }, [patchState, rememberActive])

  const saveGuest = (conversation: Conversation) => {
    guestHistory.current = [conversation, ...guestHistory.current.filter((item) => item.id !== conversation.id)]
    setHistory([...guestHistory.current])
    setTotal(guestHistory.current.length)
    if (!guestStorageReady.current) {
      setHistoryError('Browser storage is unavailable. This chat will remain in memory until you leave the page.')
      return
    }
    try { writeGuestHistory(guestHistory.current) }
    catch (error) { setHistoryError(errorMessage(error)) }
  }

  const sendMessage = async (question: string) => {
    const current = stateRef.current
    if (!ready || !question.trim() || !current.selectedCollection || current.isRestoring || stream.current || current.messages.some((message) => message.status === 'pending')) return
    const controller = new AbortController()
    stream.current = controller
    detailRequest.current?.abort()
    setHistoryError('')
    const messages: Message[] = [...current.messages, { role: 'user', content: question }]
    let conversationId = current.conversationId
    let guestConversation: Conversation | undefined
    let answer = ''
    let sources: SourceRef[] = []
    let steps: ThinkingStep[] = []
    let thinkingMs: number | undefined
    const askedAt = Date.now()
    const showAnswer = (status: NonNullable<Message['status']>) => {
      if (!mounted.current) return
      const nextMessages: Message[] = [...messages, { role: 'assistant', content: answer, status, sources, steps, thinkingMs }]
      patchState({ messages: nextMessages })
      if (guestConversation) saveGuest({ ...guestConversation, messages: nextMessages, updated_at: new Date().toISOString() })
    }
    patchState({ isLoading: true, messages: [...messages, { role: 'assistant', content: '', status: 'pending' }] })
    try {
      if (userId) {
        if (!conversationId) conversationId = (await conversationsApi.create(current.selectedCollection.id, controller.signal)).data.id
      } else {
        const now = new Date().toISOString()
        guestConversation = guestHistory.current.find((item) => item.id === current.conversationId) || {
          id: `guest_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          title: conversationTitle(question),
          collection_id: current.selectedCollection.id, collection_name: current.selectedCollection.collection_name,
          created_at: now, updated_at: now, messages: [],
        }
        conversationId = guestConversation.id
      }
      if (!mounted.current || controller.signal.aborted) return
      patchState({ conversationId })
      rememberActive(conversationId)
      showAnswer('pending')
      for await (const event of streamAnswer(current.selectedCollection.id, question, controller.signal, userId ? conversationId! : undefined)) {
        if (event.kind === 'sources') sources = event.sources
        else if (event.kind === 'status') steps = [...steps, { stage: event.stage, detail: event.detail, at: Date.now() }]
        else {
          // Thinking ends where the answer begins, not where the stream does.
          if (!answer) thinkingMs = Date.now() - askedAt
          answer += event.text
        }
        showAnswer('pending')
      }
      answer ||= 'No response received.'
      showAnswer('completed')
      if (userId) {
        try {
          const saved = fromResponse((await conversationsApi.get(conversationId!, controller.signal)).data)
          // The server never stores the trace, so carry this turn's own back onto it.
          const restored = saved.messages.map((message, index) =>
            index === saved.messages.length - 1 && message.role === 'assistant' ? { ...message, steps, thinkingMs } : message
          )
          if (mounted.current && !controller.signal.aborted) patchState({ messages: restored })
        } catch (error) {
          if (mounted.current && !controller.signal.aborted) setHistoryError(`Could not verify the saved answer: ${errorMessage(error)}`)
        }
      }
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) {
        answer ||= errorMessage(error)
        showAnswer('failed')
        setHistoryError(errorMessage(error))
      }
    } finally {
      if (stream.current === controller) stream.current = null
      if (mounted.current) {
        patchState({ isLoading: false })
        void refreshHistory()
      }
    }
  }

  const deleteConversation = async (id: string) => {
    if (stream.current || deletingId) return
    setDeletingId(id)
    setHistoryError('')
    try {
      if (userId) await conversationsApi.remove(id)
      else {
        const next = guestHistory.current.filter((item) => item.id !== id)
        if (guestStorageReady.current) writeGuestHistory(next)
        guestHistory.current = next
      }
      if (!mounted.current) return
      detailRequest.current?.abort()
      patchState({ isRestoring: false })
      if (stateRef.current.conversationId === id) newChat()
      await refreshHistory()
    } catch (error) { if (mounted.current) setHistoryError(errorMessage(error)) }
    finally { if (mounted.current) setDeletingId(null) }
  }

  return {
    state, history, historyLoading, historyError, deletingId,
    hasMore: history.length < total, isGuest: !userId,
    sendMessage, newChat, openConversation, deleteConversation,
    refreshHistory: () => { setHistoryError(''); void refreshHistory() },
    loadMore: () => { void refreshHistory(history.length) },
  }
}
