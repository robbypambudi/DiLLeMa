import { useState } from 'react'
import { Brain, Check, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { cn } from '@/shared/lib/utils'
import type { StageDetail, ThinkingStep } from '../types'

/** What each pipeline stage is called while it runs, and once it is done. */
const STAGES: Record<string, { running: (detail: StageDetail) => string; done: (detail: StageDetail) => string }> = {
  augmenting: {
    running: () => 'Rephrasing your question',
    done: () => 'Rephrased your question',
  },
  answering_locally: {
    running: (detail) => LOCAL_INTENT[String(detail.intent ?? '')] ?? LOCAL_INTENT[''],
    done: (detail) => LOCAL_INTENT[String(detail.intent ?? '')] ?? LOCAL_INTENT[''],
  },
  rewritten: {
    running: (detail) => `Searching as “${detail.query ?? ''}”`,
    done: (detail) => `Searched as “${detail.query ?? ''}”`,
  },
  following_up: {
    running: () => 'Reading this as a follow-up',
    done: () => 'Read this as a follow-up',
  },
  searching: {
    running: (detail) => `Searching ${detail.collection ?? 'your documents'}`,
    done: (detail) => `Searched ${detail.collection ?? 'your documents'}${count(detail.queries) > 1 ? ` with ${detail.queries} phrasings` : ''}`,
  },
  graph: {
    running: () => 'Checking the knowledge graph',
    done: () => 'Checked the knowledge graph',
  },
  checking: {
    running: () => 'Checking whether your documents cover this',
    done: (detail) => `Checked ${plural(detail.passages, 'passage')} for a match`,
  },
  ranking: {
    running: (detail) => `Ranking ${plural(detail.candidates, 'passage')}`,
    done: (detail) => `Ranked ${plural(detail.candidates, 'passage')}`,
  },
  reading: {
    running: (detail) => `Reading ${plural(detail.passages, 'excerpt')}`,
    done: (detail) => `Read ${plural(detail.passages, 'excerpt')}`,
  },
  generating: {
    running: (detail) => `Writing an answer from ${plural(detail.documents, 'document')}`,
    done: (detail) => `Used ${plural(detail.documents, 'document')}`,
  },
  no_evidence: {
    running: () => 'No passage matched your question',
    done: () => 'No passage matched your question',
  },
  out_of_scope: {
    running: (detail) => outOfScope(detail),
    done: (detail) => outOfScope(detail),
  },
}

/** Answered from what this collection is, rather than from what it says. */
const LOCAL_INTENT: Record<string, string> = {
  '': 'Answered from this collection',
  capability: 'Listed what this collection holds',
  small_talk: 'Said hello',
  too_short: 'Asked for a fuller question',
  no_words: 'Asked for a fuller question',
}

/** Why the question was stopped early, phrased for the person who asked it. */
const OUT_OF_SCOPE: Record<string, string> = {
  '': 'This question is outside the selected collection',
  small_talk: 'No question to search for',
  too_short: 'The question is too short to search',
  no_words: 'The question has no words to search for',
  empty_collection: 'This collection has no indexed documents',
  no_relevant_passage: 'No document in this collection covers this',
}

function outOfScope(detail: StageDetail): string {
  return OUT_OF_SCOPE[String(detail.reason ?? '')] ?? OUT_OF_SCOPE['']
}

function count(value: StageDetail[string] | undefined): number {
  return typeof value === 'number' ? value : Number(value) || 0
}

function plural(value: StageDetail[string] | undefined, noun: string): string {
  const total = count(value)
  return `${total} ${noun}${total === 1 ? '' : 's'}`
}

function label(step: ThinkingStep, running: boolean): string {
  const stage = STAGES[step.stage]
  const detail = step.detail ?? {}
  if (!stage) return step.stage.replace(/_/g, ' ')
  return running ? stage.running(detail) : stage.done(detail)
}

interface ThinkingTraceProps {
  steps?: ThinkingStep[]
  /** The turn is still streaming: the last step is what the system is doing now. */
  active: boolean
  thinkingMs?: number
}

export function ThinkingTrace({ steps = [], active, thinkingMs }: ThinkingTraceProps) {
  const [open, setOpen] = useState(false)

  if (!steps.length) {
    // The first stage has not arrived yet, so say only what is certain.
    return active ? (
      <div role="status" className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        <span className="text-xs">Working on your question…</span>
      </div>
    ) : null
  }

  if (active) {
    const current = steps[steps.length - 1]
    return (
      <div role="status" aria-live="polite" className="mb-2 space-y-1.5 border-l-2 border-primary/30 pl-3 text-xs text-muted-foreground">
        {steps.slice(0, -1).map((step, index) => (
          <div key={index} className="flex items-center gap-2">
            <Check className="h-3 w-3 shrink-0 text-primary/70" />
            <span>{label(step, false)}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-foreground">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
          <span>{label(current, true)}</span>
          <span className="flex gap-0.5" aria-hidden>
            <span className="h-1 w-1 animate-bounce rounded-full bg-current" />
            <span className="h-1 w-1 animate-bounce rounded-full bg-current" style={{ animationDelay: '0.1s' }} />
            <span className="h-1 w-1 animate-bounce rounded-full bg-current" style={{ animationDelay: '0.2s' }} />
          </span>
        </div>
      </div>
    )
  }

  const seconds = thinkingMs ? Math.max(thinkingMs, 100) / 1000 : null

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <Brain className="h-3.5 w-3.5 text-primary" />
        <span>{seconds ? `Thought for ${seconds.toFixed(1)}s` : 'Thought before answering'}</span>
        <span className="text-muted-foreground/70">· {steps.length} steps</span>
      </button>
      {open && (
        <div className={cn('mt-1.5 space-y-1.5 border-l-2 border-border pl-3 text-xs text-muted-foreground')}>
          {steps.map((step, index) => (
            <div key={index} className="flex items-center gap-2">
              <Check className="h-3 w-3 shrink-0 text-primary/70" />
              <span>{label(step, false)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
