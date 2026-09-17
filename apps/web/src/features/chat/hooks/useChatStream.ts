import { useChat } from './useChat'

export function useChatStream() {
  const { state, sendMessage } = useChat()
  return {
    send: sendMessage,
    selectedCollection: state.selectedCollection,
    isLoading: state.isLoading || state.isRestoring || state.messages.some((message) => message.status === 'pending'),
  }
}
