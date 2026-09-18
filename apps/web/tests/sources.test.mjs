import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dropSourceFooter, formatPages, pageLabelFor, renderSourceFooter } from '../.test-build/sources.mjs'

const answer = '<p>Ringkasan.</p><ol><li>Fakta [S1].</li></ol>'
const footer = '<p><b>Sumber konteks:</b></p><ul><li>[S1] RENSTRA.pdf, halaman 19</li></ul>'

test('a stored source list is removed so the chips below do not repeat it', () => {
  assert.equal(dropSourceFooter(answer + footer), answer)
  // Older answers wrote the heading without the surrounding markup.
  assert.equal(dropSourceFooter(`${answer}Sumber konteks: RENSTRA.pdf`), answer)
  assert.equal(dropSourceFooter(`${answer}<b>Sumber Konteks :</b> x`), answer)
})

test('an answer without a source list is left untouched', () => {
  assert.equal(dropSourceFooter(answer), answer)
  assert.equal(dropSourceFooter(''), '')
})

test('exports rebuild the list, escaping file names and quotes', () => {
  const html = renderSourceFooter([
    { index: 1, file_id: 'a', file_name: 'RENSTRA.pdf', pages: [19, 122], quote: 'kutipan', snippets: [] },
    { index: 2, file_id: 'b', file_name: '<script>.pdf', pages: [], quote: '', snippets: [] },
  ])
  assert.match(html, /<li>\[S1\] RENSTRA\.pdf, halaman 19, 122 — kutipan<\/li>/)
  assert.match(html, /<li>\[S2\] &lt;script&gt;\.pdf<\/li>/)
  assert.equal(renderSourceFooter([]), '')
})

test('a page is cited by the number printed on it, not its index', () => {
  const source = {
    index: 1,
    file_id: 'a',
    file_name: 'RENSTRA.pdf',
    pages: [3, 12],
    page_labels: ['iii', null],
    quote: '',
    snippets: [],
  }
  assert.equal(formatPages(source), 'halaman iii, 12')
  assert.equal(pageLabelFor(source, 3), 'iii')
  // A page without a label, or one the source never cited, keeps its number.
  assert.equal(pageLabelFor(source, 12), '12')
  assert.equal(pageLabelFor(source, 99), '99')
})

test('sources indexed before page labels existed still render', () => {
  const source = { index: 1, file_id: 'a', file_name: 'x.pdf', pages: [7], quote: '', snippets: [] }
  assert.equal(formatPages(source), 'halaman 7')
  assert.equal(formatPages({ ...source, pages: [] }), '')
})
