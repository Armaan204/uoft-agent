function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function renderInline(text, keyPrefix) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g
  const parts = text.split(pattern).filter(Boolean)

  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`

    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }

    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch) {
      return (
        <a key={key} href={linkMatch[2]} target="_blank" rel="noreferrer">
          {linkMatch[1]}
        </a>
      )
    }

    return part
  })
}

function renderTable(lines, keyPrefix) {
  const headers = splitTableRow(lines[0])
  const rows = lines.slice(2).map(splitTableRow)

  return (
    <div className="msg-table-wrap" key={keyPrefix}>
      <table className="msg-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={`${keyPrefix}-head-${index}`}>{renderInline(header, `${keyPrefix}-head-inline-${index}`)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${keyPrefix}-row-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${keyPrefix}-cell-${rowIndex}-${cellIndex}`}>
                  {renderInline(cell, `${keyPrefix}-cell-inline-${rowIndex}-${cellIndex}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function parseBlocks(text) {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (!normalized) return []

  const lines = normalized.split('\n')
  const blocks = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const codeLines = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push({ type: 'code', content: codeLines.join('\n') })
      continue
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      const level = trimmed.match(/^#+/)[0].length
      blocks.push({ type: 'heading', level, content: trimmed.replace(/^#{1,6}\s+/, '') })
      index += 1
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push({ type: 'hr' })
      index += 1
      continue
    }

    if (trimmed.includes('|') && index + 1 < lines.length && /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*$/.test(lines[index + 1])) {
      const tableLines = [line, lines[index + 1]]
      index += 2
      while (index < lines.length && lines[index].trim().includes('|')) {
        tableLines.push(lines[index])
        index += 1
      }
      blocks.push({ type: 'table', lines: tableLines })
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'ol', items })
      continue
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      const items = []
      while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*+]\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'ul', items })
      continue
    }

    const paragraphLines = []
    while (index < lines.length) {
      const next = lines[index].trim()
      if (
        !next ||
        next.startsWith('```') ||
        /^#{1,6}\s+/.test(next) ||
        /^(-{3,}|\*{3,}|_{3,})$/.test(next) ||
        /^\d+\.\s+/.test(next) ||
        /^[-*+]\s+/.test(next) ||
        (next.includes('|') && index + 1 < lines.length && /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*$/.test(lines[index + 1]))
      ) {
        break
      }
      paragraphLines.push(lines[index].trim())
      index += 1
    }
    blocks.push({ type: 'p', content: paragraphLines.join(' ') })
  }

  return blocks
}

export default function MarkdownMessage({ text }) {
  const blocks = parseBlocks(text)

  return (
    <div className="msg-markdown">
      {blocks.map((block, index) => {
        const key = `block-${index}`

        if (block.type === 'heading') {
          if (block.level <= 2) return <h3 key={key}>{renderInline(block.content, `${key}-inline`)}</h3>
          return <h4 key={key}>{renderInline(block.content, `${key}-inline`)}</h4>
        }

        if (block.type === 'hr') {
          return <hr key={key} />
        }

        if (block.type === 'table') {
          return renderTable(block.lines, key)
        }

        if (block.type === 'ol') {
          return (
            <ol key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-item-${itemIndex}`}>{renderInline(item, `${key}-item-inline-${itemIndex}`)}</li>
              ))}
            </ol>
          )
        }

        if (block.type === 'ul') {
          return (
            <ul key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-item-${itemIndex}`}>{renderInline(item, `${key}-item-inline-${itemIndex}`)}</li>
              ))}
            </ul>
          )
        }

        if (block.type === 'code') {
          return (
            <pre key={key}>
              <code>{block.content}</code>
            </pre>
          )
        }

        return <p key={key}>{renderInline(block.content, `${key}-inline`)}</p>
      })}
    </div>
  )
}
