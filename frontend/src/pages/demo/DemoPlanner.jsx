import { useState } from 'react'

import { useDemoData } from '../../context/DemoDataContext'

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2.5 7.5 6 11 11.5 3" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="7" cy="7" r="5.5" />
      <path d="M7 4.5V7l2 1.5" />
    </svg>
  )
}

function DotIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="7" cy="7" r="5.5" />
    </svg>
  )
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2 4.5 6 8l4-3.5" />
    </svg>
  )
}

function StatusIcon({ status }) {
  if (status === 'satisfied') return <CheckIcon />
  if (status === 'in_progress') return <ClockIcon />
  return <DotIcon />
}

function creditsLabel(item) {
  if (item.type === 'required') return `${item.credits ?? 0.5} cr`
  const needed = item.credits_needed ?? item.credits ?? 0
  const sat = item.credits_satisfied ?? 0
  if (sat >= needed) return `${sat} cr`
  return `${sat} / ${needed} cr`
}

function coursesList(item) {
  if (item.satisfied_by?.length) return item.satisfied_by.join(', ')
  if (item.in_progress_by?.length) return item.in_progress_by.join(', ') + ' (in progress)'
  if (item.courses_needed?.length) return item.courses_needed.join(' or ')
  if (item.courses?.length) return item.courses.join(' or ')
  return ''
}

function GradItem({ item }) {
  const courses = coursesList(item)
  return (
    <div className={`grad-item grad-item--${item.status}`}>
      <div className="grad-item-main">
        <span className={`grad-item-icon grad-item-icon--${item.status}`}><StatusIcon status={item.status} /></span>
        <div className="grad-item-body">
          <span className="grad-item-label">{item.label || item.id}</span>
          {courses && <span className="grad-item-courses">{courses}</span>}
        </div>
        <span className="grad-item-credits">{creditsLabel(item)}</span>
      </div>
    </div>
  )
}

function GradGroup({ group }) {
  const [expanded, setExpanded] = useState(group.status !== 'satisfied')
  return (
    <div className={`grad-group grad-group--${group.status}`}>
      <button type="button" className="grad-group-header" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
        <span className={`grad-group-icon grad-group-icon--${group.status}`}><StatusIcon status={group.status} /></span>
        <span className="grad-group-label">{group.label}</span>
        <span className="grad-group-credits">{group.credits_satisfied} / {group.credits_required} cr</span>
        <span className={`grad-group-chevron${expanded ? ' open' : ''}`}><ChevronDown /></span>
      </button>
      {expanded && (
        <div className="grad-group-items">
          {group.items.map((item) => <GradItem key={item.id} item={item} />)}
        </div>
      )}
    </div>
  )
}

function CoopSection({ coop }) {
  const allItems = [...(coop.preparation ?? []), ...(coop.search_courses ?? []), ...(coop.work_term_courses ?? [])]
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="grad-section">
      <div className="section-label">Co-op Requirements</div>
      <div className={`grad-group grad-group--${coop.work_terms_status}`}>
        <button type="button" className="grad-group-header" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
          <span className={`grad-group-icon grad-group-icon--${coop.work_terms_status}`}><StatusIcon status={coop.work_terms_status} /></span>
          <span className="grad-group-label">Work Terms & Co-op Courses</span>
          <span className="grad-group-credits">{coop.work_terms_completed} / {coop.work_terms_required} work terms</span>
          <span className={`grad-group-chevron${expanded ? ' open' : ''}`}><ChevronDown /></span>
        </button>
        {expanded && (
          <div className="grad-group-items">
            {allItems.map((item) => <GradItem key={item.id} item={item} />)}
          </div>
        )}
      </div>
    </div>
  )
}

const SECTION_LABELS = { core: 'Core Requirements', stream: 'Stream Requirements' }

export default function DemoPlanner() {
  const { degreePlanner } = useDemoData()
  const programs = degreePlanner

  return (
    <div className="grad-page rise">
      <div style={{
        background: 'var(--yellow-bg)',
        borderLeft: '3px solid var(--yellow)',
        borderRadius: 8,
        padding: '10px 14px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        fontSize: 13,
        lineHeight: 1.5,
      }}>
        <span style={{ flexShrink: 0, marginTop: 1 }}>⚠️</span>
        <span style={{ color: 'var(--text)' }}>
          This is sample degree progress data for demonstration purposes. Sign in and import your ACORN data to see your real graduation progress.
        </span>
      </div>

      {programs.map((prog) => {
        const pct = prog.program_credits_required > 0
          ? Math.min(100, (prog.credits_satisfied / prog.program_credits_required) * 100)
          : 0
        const fillClass = pct >= 75 ? 'fill-safe' : pct >= 40 ? 'fill-track' : 'fill-risk'

        const sectionMap = new Map()
        for (const group of (prog.groups ?? [])) {
          const sec = group.section || 'other'
          if (!sectionMap.has(sec)) sectionMap.set(sec, [])
          sectionMap.get(sec).push(group)
        }

        return (
          <div key={prog.program_name} style={{ marginBottom: 48 }}>
            <div className="grad-header">
              <div className="grad-header-top">
                <div>
                  <div className="course-code-tag">
                    <span className="status-pip" />
                    Degree Audit · {prog.academic_year}
                  </div>
                  <h1 className="grad-program-name">{prog.program_name}</h1>
                </div>
              </div>
              <div className="grad-credit-summary">
                <span className="grad-credit-main">
                  <strong>{prog.credits_satisfied}</strong>
                  <span className="grad-credit-denom"> / {prog.program_credits_required} credits</span>
                </span>
                {prog.credits_in_progress > 0 && (
                  <span className="grad-credit-ip">+{prog.credits_in_progress} IP</span>
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
                  {groups.map((group) => <GradGroup key={group.id} group={group} />)}
                </div>
              ))}
              {prog.is_coop && prog.coop && <CoopSection coop={prog.coop} />}
            </div>
          </div>
        )
      })}
    </div>
  )
}
