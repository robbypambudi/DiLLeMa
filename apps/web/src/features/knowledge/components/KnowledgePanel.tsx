import { ErrorBanner } from '@/shared/components/ErrorBanner'
import { Button } from '@/shared/components/ui/Button'
import type { DocumentFile } from '@/features/files/types'
import type { ClaimStatus } from '../types'
import { useKnowledge } from '../hooks/useKnowledge'

interface KnowledgePanelProps {
  collectionId: string
  files: Pick<DocumentFile, 'id' | 'file_name' | 'status'>[]
}

export function KnowledgePanel({ collectionId, files }: KnowledgePanelProps) {
  const { available, profile, setProfile, enabled, setEnabled, jobs, claims, status,
    setStatus, offset, setOffset, fileId, setFileId, busy, error, loaded, save, extract, review } = useKnowledge(collectionId)

  return (
    <section className="surface-card space-y-5 p-5 sm:p-7">
      <div>
        <h2 className="text-lg font-semibold">Knowledge graph</h2>
        <p className="mt-1 text-sm text-muted-foreground">Extract relationships and check their sources. Approved claims can help answer questions across documents.</p>
      </div>
      <ErrorBanner message={error} />
      {!loaded ? <p className="text-sm text-muted-foreground">Loading knowledge settings…</p> : !available ? (
        <p className="text-sm text-muted-foreground">
          Knowledge extraction is off. Set <code className="rounded bg-muted px-1 py-0.5 text-xs">KG_ENABLED=true</code> in <code className="rounded bg-muted px-1 py-0.5 text-xs">apps/.env</code> and restart the dashboard API.
        </p>
      ) : (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={busy} />
            Enable knowledge extraction for this collection
          </label>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Extraction schema</summary>
            <p className="my-2 text-sm text-muted-foreground">Define entity types, relationships, and extraction instructions. Saving a changed schema requires extracting documents again.</p>
            <label htmlFor={`schema-${collectionId}`} className="sr-only">Knowledge extraction schema JSON</label>
            <textarea id={`schema-${collectionId}`} className="field-control min-h-[260px] font-mono text-xs" value={profile} onChange={(e) => setProfile(e.target.value)} disabled={busy} spellCheck={false} />
          </details>
          <Button size="sm" onClick={save} disabled={busy}>Save knowledge settings</Button>
          <div className="flex flex-wrap items-end gap-3 border-t pt-4">
            <div className="min-w-0 flex-1 space-y-2">
              <label className="field-label" htmlFor={`extract-${collectionId}`}>Document to extract</label>
              <select id={`extract-${collectionId}`} className="field-control w-full" value={fileId} onChange={(e) => setFileId(e.target.value)} disabled={busy}>
                <option value="">Select an indexed document</option>
                {files.filter((file) => file.status === 'completed').map((file) => <option key={file.id} value={file.id}>{file.file_name}</option>)}
              </select>
            </div>
            <Button disabled={busy || !enabled || !fileId} onClick={extract}>Extract knowledge</Button>
          </div>
          {jobs.length > 0 && <ul className="space-y-2 text-sm" aria-label="Extraction jobs">
            {jobs.map((job) => <li key={job.id} className="rounded-lg border p-3">
              <span className="font-medium">{job.file_name}</span> — {job.status}
              {job.error && <p className="mt-1 text-destructive">{job.error}</p>}
            </li>)}
          </ul>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <h3 className="font-medium">Review extracted claims</h3>
            <label className="flex items-center gap-2 text-sm">Status
              <select className="field-control" value={status} onChange={(e) => { setStatus(e.target.value as ClaimStatus); setOffset(0) }} disabled={busy}>
                <option value="pending">Pending review</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
              </select>
            </label>
          </div>
          <p className="text-sm text-muted-foreground">Check the full source, conditions, and exceptions before approving. Re-extraction replaces previous claims and requires a new review.</p>
          {claims.length === 0 && <p className="text-sm text-muted-foreground">No claims in this view.</p>}
          {claims.map((claim) => <article key={claim.id} className="space-y-3 rounded-lg border p-4">
            <p className="break-words text-sm font-medium">{claim.subject_name} → {claim.predicate} → {claim.object_name}</p>
            <p className="text-sm">{claim.statement}</p>
            <dl className="space-y-1 text-sm">
              {Object.entries(claim.qualifiers).filter(([, value]) => value !== null && value !== false).map(([key, value]) => <div key={key}><dt className="inline font-medium">{key}: </dt><dd className="inline break-words">{String(value)}</dd></div>)}
            </dl>
            <blockquote className="whitespace-pre-wrap border-l-2 border-primary pl-3 text-sm">{claim.quote}</blockquote>
            <p className="text-xs text-muted-foreground">{claim.file_name}{claim.page ? ` · Page ${claim.page}` : ''}</p>
            <details><summary className="cursor-pointer text-sm">Read source context</summary><p className="mt-2 whitespace-pre-wrap break-words text-sm">{claim.text}</p></details>
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || status === 'approved'} onClick={() => review(claim.id, 'approved')}>Approve</Button>
              <Button size="sm" variant="outline" disabled={busy || status === 'rejected'} onClick={() => review(claim.id, 'rejected')}>Reject</Button>
            </div>
          </article>)}
          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button>
            <span className="text-sm">Page {offset / 20 + 1}</span>
            <Button size="sm" variant="outline" disabled={busy || claims.length < 20} onClick={() => setOffset(offset + 20)}>Next</Button>
          </div>
        </>
      )}
    </section>
  )
}
