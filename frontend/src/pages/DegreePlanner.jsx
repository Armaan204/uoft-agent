import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import client from '../api/client'

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2.5 7.5 6 11 11.5 3" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="7" cy="7" r="5.5" />
      <path d="M7 4.5V7l2 1.5" />
    </svg>
  )
}

function DotIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
      strokeWidth="2" aria-hidden>
      <circle cx="7" cy="7" r="5.5" />
    </svg>
  )
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2 4.5 6 8l4-3.5" />
    </svg>
  )
}

function StatusIcon({ status }) {
  if (status === 'satisfied')   return <CheckIcon />
  if (status === 'in_progress') return <ClockIcon />
  return <DotIcon />
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function creditsLabel(item) {
  if (item.type === 'required') {
    return `${item.credits ?? 0.5} cr`
  }
  const needed = item.credits_needed ?? item.credits ?? 0
  const sat = item.credits_satisfied ?? 0
  if (sat >= needed) return `${sat} cr`
  return `${sat} / ${needed} cr`
}

function coursesList(item) {
  if (item.satisfied_by?.length)   return item.satisfied_by.join(', ')
  if (item.in_progress_by?.length) return item.in_progress_by.join(', ') + ' (in progress)'
  if (item.courses_needed?.length) return item.courses_needed.join(' or ')
  if (item.courses?.length)        return item.courses.join(' or ')
  return ''
}

// ---------------------------------------------------------------------------
// Sub-requirement row (inside open_pool items)
// ---------------------------------------------------------------------------

function SubReq({ sr }) {
  return (
    <div className={`grad-sub-req grad-sub-req--${sr.status}`}>
      <span className={`grad-item-icon grad-item-icon--${sr.status}`}>
        <StatusIcon status={sr.status} />
      </span>
      <span className="grad-sub-req-label">{sr.label}</span>
      <span className="grad-sub-req-credits">{sr.credits_satisfied} / {sr.min_credits} cr</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Requirement item
// ---------------------------------------------------------------------------

function GradItem({ item }) {
  const hasSubReqs = item.type === 'open_pool' && item.sub_requirements?.length > 0
  const [subOpen, setSubOpen] = useState(item.status !== 'satisfied')
  const courses = coursesList(item)

  return (
    <div className={`grad-item grad-item--${item.status}`}>
      <div
        className={`grad-item-main${hasSubReqs ? ' grad-item-main--clickable' : ''}`}
        onClick={hasSubReqs ? () => setSubOpen(o => !o) : undefined}
        role={hasSubReqs ? 'button' : undefined}
        tabIndex={hasSubReqs ? 0 : undefined}
        onKeyDown={hasSubReqs ? (e) => e.key === 'Enter' && setSubOpen(o => !o) : undefined}
      >
        <span className={`grad-item-icon grad-item-icon--${item.status}`}>
          <StatusIcon status={item.status} />
        </span>
        <div className="grad-item-body">
          <span className="grad-item-label">{item.label || item.id}</span>
          {courses && <span className="grad-item-courses">{courses}</span>}
        </div>
        <span className="grad-item-credits">{creditsLabel(item)}</span>
        {hasSubReqs && (
          <span className={`grad-item-chevron${subOpen ? ' open' : ''}`}>
            <ChevronDown />
          </span>
        )}
      </div>
      {hasSubReqs && subOpen && (
        <div className="grad-sub-reqs">
          {item.sub_requirements.map(sr => <SubReq key={sr.id} sr={sr} />)}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Requirement group card
// ---------------------------------------------------------------------------

function GradGroup({ group }) {
  const [expanded, setExpanded] = useState(group.status !== 'satisfied')

  return (
    <div className={`grad-group grad-group--${group.status}`}>
      <button
        type="button"
        className="grad-group-header"
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
      >
        <span className={`grad-group-icon grad-group-icon--${group.status}`}>
          <StatusIcon status={group.status} />
        </span>
        <span className="grad-group-label">{group.label}</span>
        <span className="grad-group-credits">
          {group.credits_satisfied} / {group.credits_required} cr
        </span>
        <span className={`grad-group-chevron${expanded ? ' open' : ''}`}>
          <ChevronDown />
        </span>
      </button>

      {expanded && (
        <div className="grad-group-items">
          {group.items.map(item => <GradItem key={item.id} item={item} />)}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Co-op section
// ---------------------------------------------------------------------------

function CoopSection({ coop }) {
  const allItems = [
    ...(coop.preparation ?? []),
    ...(coop.search_courses ?? []),
    ...(coop.work_term_courses ?? []),
  ]
  const [expanded, setExpanded] = useState(coop.work_terms_status !== 'satisfied')

  return (
    <div className="grad-section">
      <div className="section-label">Co-op Requirements</div>
      <div className={`grad-group grad-group--${coop.work_terms_status}`}>
        <button
          type="button"
          className="grad-group-header"
          onClick={() => setExpanded(e => !e)}
          aria-expanded={expanded}
        >
          <span className={`grad-group-icon grad-group-icon--${coop.work_terms_status}`}>
            <StatusIcon status={coop.work_terms_status} />
          </span>
          <span className="grad-group-label">Work Terms & Co-op Courses</span>
          <span className="grad-group-credits">
            {coop.work_terms_completed} / {coop.work_terms_required} work terms
          </span>
          <span className={`grad-group-chevron${expanded ? ' open' : ''}`}>
            <ChevronDown />
          </span>
        </button>
        {expanded && (
          <div className="grad-group-items">
            {allItems.map(item => <GradItem key={item.id} item={item} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading / empty states
// ---------------------------------------------------------------------------

function GradLoading() {
  return (
    <div className="grad-page">
      <div className="grad-empty">
        <div className="grad-spinner" aria-hidden />
        <p className="grad-empty-title">Analyzing your program requirements…</p>
        <p className="grad-empty-note">
          We're scanning the academic calendar and matching your ACORN history. This might take a few seconds.
        </p>
      </div>
    </div>
  )
}

function GradEmpty({ title, note, action }) {
  return (
    <div className="grad-page">
      <div className="grad-empty rise">
        <div className="icon-wrap" style={{ marginBottom: 20 }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <p className="grad-empty-title">{title}</p>
        {note && <p className="grad-empty-note">{note}</p>}
        <div style={{ marginTop: 12 }}>
          {action}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const SECTION_LABELS = {
  core:   'Core Requirements',
  stream: 'Stream Requirements',
}

export default function DegreePlanner() {
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['graduation-progress'],
    queryFn: () =>
      client.get('/api/graduation/progress', { timeout: 90000 }).then(r => r.data),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    retry: false,
  })

  const clearMutation = useMutation({
    mutationFn: () => client.delete('/api/graduation/cache'),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['graduation-progress'] })
      refetch()
    },
  })

  if (clearMutation.isPending) return <GradLoading forceAnalyze />
  if (isLoading) return <GradLoading />

  if (isError) {
    const status = error?.response?.status
    const detail = error?.response?.data?.detail || ''
    if (status === 400 || detail.toLowerCase().includes('acorn')) {
      return (
        <GradEmpty
          title="Import your ACORN data first"
          note="Degree Planner needs your academic history to check graduation progress."
          action={<Link to="/acorn" className="btn-view grad-cta">Go to ACORN →</Link>}
        />
      )
    }
    if (status === 404) {
      return (
        <GradEmpty
          title="Program calendar not found"
          note={detail || 'Your program may not be supported yet. Contact your registrar for degree audit support.'}
          action={
            <button
              className="dashboard-refresh-btn"
              onClick={() => refetch()}
            >
              Try again
            </button>
          }
        />
      )
    }
    return (
      <GradEmpty
        title="Could not load graduation progress"
        note={detail || 'Something went wrong. Please try again.'}
        action={
          <button className="dashboard-refresh-btn" onClick={() => refetch()}>
            Try again
          </button>
        }
      />
    )
  }

  const pct = data.program_credits_required > 0
    ? Math.min(100, (data.credits_satisfied / data.program_credits_required) * 100)
    : 0
  const fillClass = pct >= 75 ? 'fill-safe' : pct >= 40 ? 'fill-track' : 'fill-risk'

  // Group by section, preserving order
  const sectionMap = new Map()
  for (const group of (data.groups ?? [])) {
    const sec = group.section || 'other'
    if (!sectionMap.has(sec)) sectionMap.set(sec, [])
    sectionMap.get(sec).push(group)
  }

  return (
    <div className="grad-page rise">
      <div className="grad-header">
        <div className="grad-header-top">
          <div>
            <div className="course-code-tag">
              <span className="status-pip" />
              Degree Audit · {data.academic_year || 'Current'}
            </div>
            <h1 className="grad-program-name">{data.program_name || 'Degree Planner'}</h1>
          </div>
          <button
            type="button"
            className={`dashboard-refresh-btn ${clearMutation.isPending ? 'refreshing' : ''}`}
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            title="Re-extract requirements from the calendar"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={clearMutation.isPending ? 'refreshing' : ''}>
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M3 21v-5h5" />
            </svg>
            {clearMutation.isPending ? 'Analyzing...' : 'Re-analyze'}
          </button>
        </div>

        <div className="grad-credit-summary">
          <span className="grad-credit-main">
            <strong>{data.credits_satisfied}</strong>
            <span className="grad-credit-denom"> / {data.program_credits_required} credits</span>
          </span>
          {data.credits_in_progress > 0 && (
            <span className="grad-credit-ip">+{data.credits_in_progress} IP</span>
          )}
        </div>

        <div className="progress-wrap" style={{ height: 12, marginBottom: 0 }}>
          <div className={`progress-fill ${fillClass}`} style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="grad-groups">
        {[...sectionMap.entries()].map(([sec, groups]) => (
          <div key={sec} className="grad-section">
            <div className="section-label">{SECTION_LABELS[sec] || sec}</div>
            {groups.map(group => <GradGroup key={group.id} group={group} />)}
          </div>
        ))}

        {data.is_coop && data.coop && <CoopSection coop={data.coop} />}
      </div>

      <div className="grad-footer">
        <Link to="/chat" state={{ initialMessage: 'Am I on track to graduate?' }} className="grad-cta">
          Ask AI about graduation →
        </Link>
      </div>
    </div>
  )
}

