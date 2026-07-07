import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import client from '../api/client'

export default function AddCourseModal({ open, onClose }) {
  const queryClient = useQueryClient()
  const dialogRef = useRef(null)
  const [courseCode, setCourseCode] = useState('')
  const [courseName, setCourseName] = useState('')
  const [term, setTerm] = useState('')
  const [weightMode, setWeightMode] = useState('syllabus')
  const [weights, setWeights] = useState([{ name: '', weight: '' }])
  const [syllabusFile, setSyllabusFile] = useState(null)
  const [parsedWeights, setParsedWeights] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      dialogRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  function resetForm() {
    setCourseCode('')
    setCourseName('')
    setTerm('')
    setWeightMode('syllabus')
    setWeights([{ name: '', weight: '' }])
    setSyllabusFile(null)
    setParsedWeights(null)
    setParsing(false)
    setSubmitting(false)
    setError('')
  }

  function handleClose() {
    resetForm()
    onClose()
  }

  function addWeightRow() {
    setWeights((prev) => [...prev, { name: '', weight: '' }])
  }

  function removeWeightRow(index) {
    setWeights((prev) => prev.filter((_, i) => i !== index))
  }

  function updateWeight(index, field, value) {
    setWeights((prev) => prev.map((w, i) => (i === index ? { ...w, [field]: value } : w)))
  }

  function getWeightsDict() {
    if (parsedWeights) return parsedWeights
    const result = {}
    for (const w of weights) {
      const name = w.name.trim()
      const val = Number.parseFloat(w.weight)
      if (name && !Number.isNaN(val) && val > 0) {
        result[name] = val
      }
    }
    return result
  }

  async function handleParseSyllabus(file) {
    if (!file) return
    setParsing(true)
    setError('')
    try {
      const tempCourse = await client.post('/api/manual-courses', {
        course_code: courseCode.trim() || 'TEMP',
        course_name: courseName.trim() || 'Temp',
        term: term.trim(),
      })
      const tempId = tempCourse.data.id

      const formData = new FormData()
      formData.append('file', file)
      const { data } = await client.post(`/api/manual-courses/${tempId}/syllabus`, formData)
      setParsedWeights(data.weights)

      const weightRows = Object.entries(data.weights).map(([name, weight]) => ({ name, weight: String(weight) }))
      setWeights(weightRows.length > 0 ? weightRows : [{ name: '', weight: '' }])

      await client.delete(`/api/manual-courses/${tempId}`)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to parse syllabus')
    } finally {
      setParsing(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (submitting) return

    const code = courseCode.trim()
    const name = courseName.trim()
    if (!code || !name) {
      setError('Course code and name are required')
      return
    }

    const weightsDict = getWeightsDict()
    if (Object.keys(weightsDict).length === 0) {
      setError('Please upload a syllabus or manually enter course weights before creating a course')
      return
    }
    const total = Object.values(weightsDict).reduce((s, v) => s + v, 0)
    if (Math.abs(total - 100) > 0.01) {
      setError(`Weights must add up to 100% (currently ${total.toFixed(1)}%)`)
      return
    }
    setSubmitting(true)
    setError('')

    try {
      const { data: created } = await client.post('/api/manual-courses', {
        course_code: code,
        course_name: name,
        term: term.trim(),
        weights: weightsDict,
      })
      queryClient.setQueryData(['dashboard'], (old) => {
        if (!old) return old
        const card = {
          id: created.id,
          course_code: code,
          name,
          term_name: term.trim(),
          current_grade: 100,
          display_grade: 100,
          letter_grade: 'A+',
          risk_flag: 'On track',
          progress_pct: 0,
          deadlines: [],
          source: 'manual',
        }
        return { ...old, courses: [...(old.courses || []), card] }
      })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      handleClose()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to create course')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  const totalWeight = weights.reduce((sum, w) => sum + (Number.parseFloat(w.weight) || 0), 0)

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}>
      <div className="add-course-modal" ref={dialogRef} tabIndex={-1} role="dialog" aria-label="Add course">
        <div className="add-course-modal-header">
          <h2>Add course</h2>
          <button type="button" className="modal-close-btn" onClick={handleClose} aria-label="Close">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="add-course-form">
          <div className="add-course-row">
            <label className="add-course-label">
              Course code
              <input type="text" value={courseCode} onChange={(e) => setCourseCode(e.target.value)} placeholder="e.g. CSC108H1" required />
            </label>
            <label className="add-course-label">
              Term
              <input type="text" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="e.g. Fall 2025" />
            </label>
          </div>

          <label className="add-course-label">
            Course name
            <input type="text" value={courseName} onChange={(e) => setCourseName(e.target.value)} placeholder="e.g. Intro to Computer Programming" required />
          </label>

          <div className="weight-mode-tabs" role="tablist">
            <button type="button" className={weightMode === 'syllabus' ? 'active' : ''} onClick={() => setWeightMode('syllabus')}>Upload syllabus</button>
            <button type="button" className={weightMode === 'manual' ? 'active' : ''} onClick={() => setWeightMode('manual')}>Enter weights</button>
          </div>

          {weightMode === 'syllabus' && (
            <div className="syllabus-upload-section">
              <input
                type="file"
                accept=".pdf,.docx"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null
                  setSyllabusFile(file)
                  setParsedWeights(null)
                  if (file) handleParseSyllabus(file)
                }}
              />
              {parsing && <p className="parse-progress">Extracting weights…</p>}
              {parsedWeights && <p className="parse-success">Weights extracted — review below</p>}
            </div>
          )}

          {(weightMode === 'manual' || parsedWeights) && (
          <div className="weight-entries">
            <div className="weight-entries-header">
              <span>Component</span>
              <span>Weight %</span>
              <span />
            </div>
            {weights.map((w, i) => (
              <div className="weight-entry-row" key={i}>
                <input
                  type="text"
                  value={w.name}
                  onChange={(e) => updateWeight(i, 'name', e.target.value)}
                  placeholder="e.g. Midterm"
                />
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="any"
                  value={w.weight}
                  onChange={(e) => updateWeight(i, 'weight', e.target.value)}
                  placeholder="%"
                />
                {weights.length > 1 && (
                  <button type="button" className="weight-remove-btn" onClick={() => removeWeightRow(i)} aria-label="Remove">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="12" height="12">
                      <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
            <button type="button" className="weight-add-btn" onClick={addWeightRow}>+ Add component</button>
            {totalWeight > 0 && (
              <div className={`weight-total${Math.abs(totalWeight - 100) < 0.01 ? ' valid' : ''}`}>
                Total: {totalWeight.toFixed(1)}%
              </div>
            )}
          </div>
          )}

          {error && <p className="add-course-error">{error}</p>}

          <div className="add-course-actions">
            <button type="button" className="btn-cancel" onClick={handleClose}>Cancel</button>
            <button type="submit" className="btn-save" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create course'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
