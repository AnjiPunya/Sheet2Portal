import type { ReactNode } from 'react'

// A deliberately small markdown subset for chatbot answers: paragraphs,
// **bold**, `code`, bullet/numbered lists and pipe tables. Everything is
// rendered as React elements (never raw HTML), so model output -- which can
// echo spreadsheet contents -- can't inject markup or scripts.

// Drop markdown backslash escapes such as "\<" or "\*".
const unescape = (text: string) => text.replace(/\\([\\`*_<>|#[\]()-])/g, '$1')

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{renderInline(part.slice(2, -2))}</strong>
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={i}>{renderInline(part.slice(1, -1))}</em>
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="rounded bg-slate-200 px-1 text-[12px]">
          {part.slice(1, -1)}
        </code>
      )
    }
    return unescape(part)
  })
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim())
}

const isTableRow = (line: string) => line.trim().startsWith('|')
const isTableDivider = (line: string) => /^\s*\|?\s*:?-{2,}/.test(line)
const bulletMatch = (line: string) => line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/)

export function ChatMarkdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (!line.trim()) {
      i++
      continue
    }

    if (isTableRow(line)) {
      const rows: string[][] = []
      while (i < lines.length && isTableRow(lines[i])) {
        if (!isTableDivider(lines[i])) rows.push(splitRow(lines[i]))
        i++
      }
      const [header, ...body] = rows
      if (!header) continue
      blocks.push(
        <div key={blocks.length} className="overflow-x-auto">
          <table className="my-1 w-full border-collapse text-xs">
            <thead>
              <tr>
                {header.map((cell, c) => (
                  <th key={c} className="border-b border-slate-300 px-1.5 py-1 text-left font-semibold">
                    {renderInline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className="border-b border-slate-200 px-1.5 py-1 align-top">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    if (bulletMatch(line)) {
      const items: string[] = []
      while (i < lines.length && bulletMatch(lines[i])) {
        items.push(bulletMatch(lines[i])![1])
        i++
      }
      blocks.push(
        <ul key={blocks.length} className="list-disc space-y-0.5 pl-4">
          {items.map((item, k) => (
            <li key={k}>{renderInline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    const paragraph: string[] = []
    while (i < lines.length && lines[i].trim() && !isTableRow(lines[i]) && !bulletMatch(lines[i])) {
      paragraph.push(lines[i].replace(/^#+\s*/, ''))
      i++
    }
    blocks.push(<p key={blocks.length}>{renderInline(paragraph.join(' '))}</p>)
  }

  return <div className="space-y-2">{blocks}</div>
}
