import { useState } from 'react'

function normalizeResult(result) {
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    return Object.entries(result)
  }
  return [['result', JSON.stringify(result)]]
}

export default function ToolCallBlock({ toolCall }) {
  const [open, setOpen] = useState(false)
  const entries = normalizeResult(toolCall.result ?? toolCall.output ?? toolCall)

  return (
    <div className={`tool-block ${open ? 'open' : ''}`}>
      <button className="tool-header" type="button" onClick={() => setOpen((value) => !value)}>
        <div className="tool-header-left">
          <div className="tool-icon">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 10V4l4-3 4 3v6" />
              <rect x="4" y="6" width="4" height="4" />
            </svg>
          </div>
          <span className="tool-name">{toolCall.name || toolCall.tool_name || 'Tool call'}</span>
        </div>
        <div className="tool-header-right">
          <span className="tool-status">Done</span>
          <span className="tool-chevron">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 2l4 4-4 4" />
            </svg>
          </span>
        </div>
      </button>
      <div className="tool-body">
        <div className="tool-body-inner">
          {entries.map(([key, value]) => (
            <div className="tool-kv" key={key}>
              <span className="tool-key">{key}</span>
              <span className="tool-val">{typeof value === 'string' ? value : JSON.stringify(value)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
