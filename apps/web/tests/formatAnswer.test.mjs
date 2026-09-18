import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatAnswer } from '../.test-build/formatAnswer.mjs'

test('markdown bullets render as a list with bold labels', () => {
  const html = formatAnswer(
    'Kode mata kuliah Sistem Operasi berbeda per kurikulum.\n' +
      '- **Kurikulum 2023**: EF234202 [S1]\n' +
      '- **Pilihan**: EF234513 [S2]'
  )
  assert.match(html, /^<p>Kode mata kuliah Sistem Operasi berbeda per kurikulum\.<\/p>/)
  assert.match(html, /<ul>\s*<li><strong>Kurikulum 2023<\/strong>: EF234202 \[S1\]<\/li>/)
  assert.match(html, /<li><strong>Pilihan<\/strong>: EF234513 \[S2\]<\/li>\s*<\/ul>/)
  assert.equal(html.includes('**'), false)
})

test('per-item source lines are dropped and items with one label are kept', () => {
  // The shape a small model produced when the prompt asked for HTML.
  const html = formatAnswer(
    'Berikut ringkasan jawaban:\n' +
      '* Judul: Kode mata kuliah Sistem Operasi adalah EF234202.\n' +
      '    * *Sumber:* Modul Handbook.pdf, halaman 29.\n' +
      '* Judul: Kode mata kuliah Sistem Operasi adalah EF234513.\n' +
      '    * *Sumber:* Modul Handbook.pdf, halaman 119.'
  )
  assert.equal(html.includes('Sumber'), false)
  assert.equal(html.includes('*'), false)
  assert.match(html, /EF234202/)
  assert.match(html, /EF234513/)
  assert.equal((html.match(/<li>/g) || []).length, 2)
})

test('glued numbered items are split and repeats removed', () => {
  const html = formatAnswer(
    'Tahapan:1. **Analisis** kebutuhan sistem2. **Desain** arsitektur sistem3. **Analisis** kebutuhan sistem'
  )
  assert.equal((html.match(/<li>/g) || []).length, 2)
  assert.match(html, /<ol>/)
})

test('html answers from history and the server footer pass through', () => {
  const html = formatAnswer(
    '<p>Ringkasan.</p><ol><li><b>A:</b> fakta [S1]</li></ol>' +
      '<p><b>Sumber konteks:</b></p><ul><li>[S1] a.pdf</li></ul>'
  )
  assert.match(html, /<p>Ringkasan\.<\/p><ol><li><b>A:<\/b> fakta \[S1\]<\/li><\/ol>/)
  assert.match(html, /<b>Sumber konteks:<\/b><\/p><ul><li>\[S1\] a\.pdf<\/li><\/ul>$/)
})

test('reasoning and code fences are removed', () => {
  assert.equal(formatAnswer('<think>hmm</think>```markdown\nHalo\n```').trim(), '<p>Halo</p>')
})
