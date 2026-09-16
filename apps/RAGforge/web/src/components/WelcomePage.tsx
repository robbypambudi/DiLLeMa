import { useNavigate } from 'react-router-dom'
import { ArrowRight, BookOpen, FileText, MessageSquare } from 'lucide-react'
import logoLight from '../../assets/logo-light.png'
import logoDark from '../../assets/logo-dark.png'

import { AppState } from '@/App'
import { useAuth } from '@/auth'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/Button'

interface WelcomePageProps {
  onCreateChat: () => void
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
}

export function WelcomePage({ onCreateChat, appState, updateState }: WelcomePageProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const toggleTheme = () => {
    updateState({ theme: appState.theme === 'light' ? 'dark' : 'light' })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b bg-surface px-4 py-4 sm:px-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <img src={logoLight} alt="" className="h-8 dark:hidden" />
            <img src={logoDark} alt="" className="hidden h-8 dark:block" />
            <span className="text-lg font-semibold tracking-tight">DiLLeMa</span>
          </div>
          <div className="flex items-center gap-2">
            {user?.role === 'admin' && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin')}>
                Admin
              </Button>
            )}
            {user ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  logout()
                  navigate('/', { replace: true })
                }}
              >
                Logout
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={() => navigate('/login')}>
                Sign in
              </Button>
            )}
            <ThemeToggle theme={appState.theme} onToggle={toggleTheme} />
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 items-center px-5 py-12 sm:px-8 sm:py-20">
        <div className="grid w-full items-center gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs font-semibold tracking-wide text-primary">
              <BookOpen className="h-3.5 w-3.5" /> YOUR DOCUMENT KNOWLEDGE SPACE
            </div>
            <h1 className="max-w-xl text-4xl font-semibold leading-[1.15] tracking-tight sm:text-5xl lg:text-6xl">
              Your documents.<br /><span className="text-primary">A clearer answer.</span>
            </h1>
            <p className="mt-6 max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg">
              Turn your document collections into a conversation. Explore ideas, find information, and get answers with DiLLeMa.
            </p>
            <Button onClick={onCreateChat} size="lg" className="mt-8">
              Create New Chat <ArrowRight className="h-4 w-4" />
            </Button>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
              Powered by a Distributed Large Language Model<br className="hidden sm:block" /> with retrieval-augmented generation.
            </p>
          </div>
          <div className="surface-card overflow-hidden">
            <div className="border-b bg-primary/5 p-6 sm:p-8">
              <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-surface text-primary">
                <MessageSquare className="h-6 w-6" />
              </span>
              <h2 className="text-xl font-semibold tracking-tight">From documents to discovery</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">A focused workspace for the knowledge you need.</p>
            </div>
            <ol className="divide-y px-6 sm:px-8">
              {[
                { icon: BookOpen, title: 'Choose a collection', description: 'Start with a collection of documents.' },
                { icon: MessageSquare, title: 'Ask your question', description: 'Explore a topic in your own words.' },
                { icon: FileText, title: 'Keep the conversation', description: 'Copy an answer or export your chat.' },
              ].map(({ icon: Icon, title, description }, index) => (
                <li key={title} className="flex items-start gap-4 py-6">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary"><Icon className="h-5 w-5" /></span>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold">{title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
                  </div>
                  <span className="pt-1 text-xs font-medium text-muted-foreground">0{index + 1}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </main>
      <footer className="border-t px-5 py-5 text-center text-xs leading-relaxed text-muted-foreground">
        Built to support the Informatics degree at{' '}
        <a className="font-medium underline decoration-border underline-offset-4 hover:text-primary" href="https://www.its.ac.id">Institut Teknologi Sepuluh Nopember Surabaya</a>
      </footer>
    </div>
  )
}
