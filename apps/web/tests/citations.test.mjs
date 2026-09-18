import assert from 'node:assert/strict'
import { test } from 'node:test'
import { linkCitations } from '../.test-build/citations.mjs'

const cited = new Set([1, 2])

test('markers with metadata become buttons carrying their index', () => {
  const html = linkCitations('<p>Transformasi [S1] menuju fase [S2].</p>', cited)
  assert.match(html, /data-citation="1"[^>]*>S1<\/button>/)
  assert.match(html, /data-citation="2"[^>]*>S2<\/button>/)
  assert.equal(html.startsWith('<p>Transformasi '), true)
})

test('a marker without metadata is left as written', () => {
  assert.equal(linkCitations('<p>Klaim [S9].</p>', cited), '<p>Klaim [S9].</p>')
  assert.equal(linkCitations('<p>Klaim [S1].</p>', new Set()), '<p>Klaim [S1].</p>')
})

test('footer rows are linked too, and markup is never rewritten', () => {
  const footer = '<p><b>Sumber konteks:</b></p><ul><li>[S1] RENSTRA.pdf, halaman 171</li></ul>'
  const html = linkCitations(footer, cited)
  assert.match(html, /<li><button[^>]*data-citation="1"[^>]*>S1<\/button> RENSTRA\.pdf, halaman 171<\/li>/)
  // Attribute values that happen to look like markers stay untouched.
  assert.equal(linkCitations('<div title="[S1]">plain</div>', cited).includes('title="[S1]"'), true)
})
