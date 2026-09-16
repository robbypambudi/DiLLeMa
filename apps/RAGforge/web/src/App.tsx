import { useState, useEffect } from 'react'
import { WelcomePage } from '@/components/WelcomePage'
import { ChatDashboard } from '@/components/ChatDashboard'
import { CollectionManager } from '@/components/CollectionManager'

export interface Collection {
  id: string
  name: string
  description: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface AppState {
  theme: 'light' | 'dark'
  collections: Collection[]
  selectedCollection: Collection | null
  messages: Message[]
  isLoading: boolean
}

function App() {
  const [currentView, setCurrentView] = useState<'welcome' | 'chat' | 'collections'>('welcome')
  const [appState, setAppState] = useState<AppState>({
    theme: 'light',
    collections: [],
    selectedCollection: null,
    messages: [{
      role: 'assistant',
      content: '👋 Welcome to our chatbot! Feel free to ask about anything.'
    }],
    isLoading: false
  })

  useEffect(() => {
    // Apply theme to document
    if (appState.theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [appState.theme])

  const updateState = (updates: Partial<AppState>) => {
    setAppState(prev => ({ ...prev, ...updates }))
  }

  return (
    <>
      {currentView === 'welcome' ? (
        <WelcomePage 
          onCreateChat={() => setCurrentView('chat')}
          appState={appState}
          updateState={updateState}
        />
      ) : currentView === 'collections' ? (
        <div className="min-h-screen bg-background">
          <div className="p-4 border-b">
            <button 
              onClick={() => setCurrentView('chat')}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              ← Back to Dashboard
            </button>
          </div>
          <CollectionManager />
        </div>
      ) : (
        <ChatDashboard 
          onBack={() => setCurrentView('welcome')}
          appState={appState}
          updateState={updateState}
          onManageCollections={() => setCurrentView('collections')}
        />
      )}
    </>
  )
}

export default App
