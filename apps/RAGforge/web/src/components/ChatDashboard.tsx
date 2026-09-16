import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { ThemeToggle } from '@/components/ThemeToggle'
import { CollectionSelector } from '@/components/CollectionSelector'
import { ChatWindow } from '@/components/ChatWindow'
import { ChatInput } from '@/components/ChatInput'
import { AppState } from '@/App'

interface ChatDashboardProps {
  onBack: () => void
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
  onManageCollections: () => void
}

export function ChatDashboard({ onBack, appState, updateState }: ChatDashboardProps) {
// export function ChatDashboard({ onBack, appState, updateState, onManageCollections }: ChatDashboardProps) {
  const toggleTheme = () => {
    updateState({ theme: appState.theme === 'light' ? 'dark' : 'light' })
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b p-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button variant="outline" size="sm" onClick={onBack}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <div className="flex items-center space-x-3">
            <img 
              src="/assets/logo-light.png" 
              alt="RAGforge" 
              className="h-8 dark:hidden"
            />
            <img 
              src="/assets/logo-dark.png" 
              alt="RAGforge" 
              className="h-8 hidden dark:block"
            />
            <h1 className="text-2xl font-semibold">D<span className="text-accent">i</span>LL<span className="text-accent">e</span>M<span className="text-accent">a</span> Chat</h1>
          </div>
        </div>
        <ThemeToggle theme={appState.theme} onToggle={toggleTheme} />
      </header>
      
      <div className="flex-1 flex overflow-hidden">
        {/* <CollectionSelector appState={appState} updateState={updateState} onManageCollections={onManageCollections} /> */}
        <CollectionSelector appState={appState} updateState={updateState} />
        
        <div className="flex-1 flex flex-col">
          <ChatWindow appState={appState} />
          <ChatInput appState={appState} updateState={updateState} />
        </div>
      </div>
    </div>
  )
}
