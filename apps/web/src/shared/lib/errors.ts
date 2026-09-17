export function errorMessage(error: unknown, fallback = 'Could not reach the server.'): string {
  return error instanceof Error ? error.message : fallback
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}
