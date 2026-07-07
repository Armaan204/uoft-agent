import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import client from '../api/client'
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

const TIME_OPTIONS = []
for (let h = 0; h < 24; h++) {
  for (const m of [0, 30]) {
    const hh = String(h).padStart(2, '0')
    const mm = String(m).padStart(2, '0')
    const suffix = h >= 12 ? 'PM' : 'AM'
    const display = `${h === 0 ? 12 : h > 12 ? h - 12 : h}:${mm} ${suffix}`
    TIME_OPTIONS.push({ value: `${hh}:${mm}`, label: display })
  }
}
TIME_OPTIONS.push({ value: '23:59', label: '11:59 PM' })

export default function DeadlineList({ deadlines, maxHeight, courses, readOnly }) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [dueDate, setDueDate] = useState(null)
  const [dueTime, setDueTime] = useState('23:59')
  const [courseId, setCourseId] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  const createMutation = useMutation({
    mutationFn: (body) => client.post('/api/manual-courses/deadlines', body),
    onSuccess: (res, body) => {
      const newDeadline = {
        course_code: body.course_code || '',
        name: body.name,
        due_at: body.due_at,
        manual_deadline_id: res.data?.id ?? null,
      }
      queryClient.setQueryData(['dashboard'], (old) => {
        if (!old) return old
        const updated = old.courses?.map((c) => {
          const match = body.course_id
            ? c.id === body.course_id
            : body.course_code && c.course_code === body.course_code
          if (match) {
            return { ...c, deadlines: [...(c.deadlines || []), newDeadline] }
          }
          return c
        }) || []
        return { ...old, courses: updated }
      })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setName('')
      setDueDate(null)
      setDueTime('23:59')
      setCourseId('')
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (deadlineId) => client.delete(`/api/manual-courses/deadlines/${deadlineId}`),
    onMutate: (deadlineId) => {
      queryClient.setQueryData(['dashboard'], (old) => {
        if (!old) return old
        const updated = old.courses?.map((c) => ({
          ...c,
          deadlines: (c.deadlines || []).filter((d) => d.manual_deadline_id !== deadlineId),
        })) || []
        return { ...old, courses: updated }
      })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  })

  function handleAdd(e) {
    e.preventDefault()
    if (!name.trim() || !dueDate || !courseId) return
    const selectedCourse = (courses || []).find((c) => String(c.id) === courseId)
    const [hh, mm] = dueTime.split(':').map(Number)
    const dateTime = new Date(dueDate)
    dateTime.setHours(hh, mm, 0, 0)
    const isManual = selectedCourse && selectedCourse.source === 'manual'
    createMutation.mutate({
      name: name.trim(),
      due_at: dateTime.toISOString(),
      course_id: isManual ? selectedCourse.id : null,
      course_code: selectedCourse ? selectedCourse.course_code : '',
    })
  }

  return (
    <div className="deadlines rise" style={maxHeight ? { maxHeight: `${maxHeight}px` } : undefined}>
      {!deadlines.length && !showForm && (
        <div className="empty-card">No assignments due in the next 14 days.</div>
      )}

      {deadlines.map((deadline) => {
        const tone = deadlineTone(deadline.due_at)
        return (
          <div className="deadline-item" key={`${deadline.course_code}-${deadline.name}-${deadline.due_at}`}>
            <span className="dl-code">{displayCourseCode(deadline.course_code)}</span>
            <span className="dl-name">{deadline.name}</span>
            <span className={`dl-due ${tone}`}>
              <span className={`dl-dot dot-${tone}`} />
              {formatDue(deadline.due_at)}
              {deadline.manual_deadline_id && (
                confirmDeleteId === deadline.manual_deadline_id ? (
                  <span className="dl-delete-confirm">
                    <button type="button" className="dl-confirm-yes" onClick={() => { deleteMutation.mutate(deadline.manual_deadline_id); setConfirmDeleteId(null) }}>Delete</button>
                    <button type="button" className="dl-confirm-no" onClick={() => setConfirmDeleteId(null)}>Cancel</button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="dl-delete-btn"
                    onClick={() => setConfirmDeleteId(deadline.manual_deadline_id)}
                    aria-label="Delete deadline"
                  >
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="12" height="12">
                      <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                    </svg>
                  </button>
                )
              )}
            </span>
          </div>
        )
      })}

      {!readOnly && showForm && (
        <form className="deadline-add-form" onSubmit={handleAdd}>
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)} required>
            <option value="" disabled>Select course</option>
            {(courses || []).map((c) => (
              <option key={c.id} value={String(c.id)}>{displayCourseCode(c.course_code)}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Deadline name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div className="deadline-datetime-row">
            <DatePicker
              selected={dueDate}
              onChange={(date) => setDueDate(date)}
              placeholderText="Select date"
              dateFormat="MMM d, yyyy"
              minDate={new Date()}
              className="deadline-datepicker-input"
              popperPlacement="top-start"
              portalId="datepicker-portal"
              required
            />
            <select value={dueTime} onChange={(e) => setDueTime(e.target.value)}>
              {TIME_OPTIONS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="deadline-add-actions">
            <button type="submit" className="btn-save" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Adding…' : 'Add'}
            </button>
            <button type="button" className="btn-cancel" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      {!readOnly && (
        <button type="button" className="deadline-add-btn" onClick={() => setShowForm((v) => !v)}>
          + Add deadline
        </button>
      )}
    </div>
  )
}
