import { displayCourseCode } from '../utils/courseCode'

function deadlineTone(dueAt) {
  const diffMs = new Date(dueAt).getTime() - Date.now()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)
  if (diffDays < 2) return 'urgent'
  if (diffDays < 5) return 'soon'
  return 'safe'
}

function formatDue(dueAt) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date(dueAt))
}

export default function DeadlineList({ deadlines }) {
  if (!deadlines.length) {
    return <div className="empty-card">No assignments due in the next 14 days.</div>
  }

  return (
    <div className="deadlines rise">
      {deadlines.map((deadline) => {
        const tone = deadlineTone(deadline.due_at)
        return (
          <div className="deadline-item" key={`${deadline.course_code}-${deadline.name}-${deadline.due_at}`}>
            <span className="dl-code">{displayCourseCode(deadline.course_code)}</span>
            <span className="dl-name">{deadline.name}</span>
            <span className={`dl-due ${tone}`}>
              <span className={`dl-dot dot-${tone}`} />
              {formatDue(deadline.due_at)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
