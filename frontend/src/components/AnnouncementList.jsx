import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import client from '../api/client'
import { displayCourseCode } from '../utils/courseCode'

function formatPosted(postedAt) {
  if (!postedAt) return 'Recently posted'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(new Date(postedAt))
}

function AnnouncementModal({ announcement, onClose }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['announcement-latest', String(announcement.course_id)],
    queryFn: async () => {
      const response = await client.get(`/api/courses/${announcement.course_id}/announcements/latest`)
      return response.data
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    enabled: Boolean(announcement),
  })

  useEffect(() => {
    function handleEscape(event) {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', handleEscape)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [onClose])

  const modalTitle = data?.title || announcement.title
  const modalPostedAt = data?.posted_at || announcement.posted_at

  return (
    <div className="announcement-modal-overlay" onClick={onClose} role="presentation">
      <div
        className="announcement-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="announcement-modal-title"
      >
        <div className="announcement-modal-head">
          <div>
            <div className="announcement-code">{displayCourseCode(announcement.course_code)}</div>
            <div className="announcement-modal-date">{formatPosted(modalPostedAt)}</div>
            <h2 className="announcement-modal-title" id="announcement-modal-title">{modalTitle}</h2>
          </div>
          <button className="announcement-modal-close" type="button" onClick={onClose} aria-label="Close announcement">
            ×
          </button>
        </div>

        <div className="announcement-modal-body">
          {isLoading ? (
            <div className="dashboard-loading-card announcement-loading-card" aria-live="polite">
              <div className="loading-spinner" aria-hidden="true" />
              <div className="dashboard-loading-copy">Loading announcement…</div>
            </div>
          ) : null}

          {error ? (
            <div className="empty-card">Failed to load the full announcement.</div>
          ) : null}

          {!isLoading && !error ? (
            data?.body_html ? (
              <div className="announcement-modal-content" dangerouslySetInnerHTML={{ __html: data.body_html }} />
            ) : (
              <div className="empty-card">{data?.body_text || 'No announcement body was available.'}</div>
            )
          ) : null}
        </div>

        <div className="announcement-modal-actions">
          <button className="acorn-secondary-btn" type="button" onClick={onClose}>
            Close
          </button>
          {announcement.url ? (
            <a className="acorn-primary-btn" href={announcement.url} target="_blank" rel="noreferrer">
              Open in Quercus
            </a>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default function AnnouncementList({ announcements }) {
  const [selectedAnnouncement, setSelectedAnnouncement] = useState(null)

  if (!announcements.length) {
    return <div className="empty-card">No recent announcements right now.</div>
  }

  return (
    <>
      <div className="deadlines announcements rise">
        {announcements.map((announcement) => (
          <button
            className="announcement-item"
            type="button"
            key={`${announcement.course_id}-${announcement.title}-${announcement.posted_at || 'na'}`}
            onClick={() => setSelectedAnnouncement(announcement)}
          >
            <div className="announcement-code">{displayCourseCode(announcement.course_code)}</div>
            <div className="announcement-body">
              <div className="announcement-title">{announcement.title}</div>
              <div className="announcement-preview">{announcement.preview || 'Click to read the full announcement.'}</div>
            </div>
            <div className="announcement-date">{formatPosted(announcement.posted_at)}</div>
          </button>
        ))}
      </div>

      {selectedAnnouncement ? (
        <AnnouncementModal announcement={selectedAnnouncement} onClose={() => setSelectedAnnouncement(null)} />
      ) : null}
    </>
  )
}
