import { displayCourseCode } from '../utils/courseCode'

function formatPosted(postedAt) {
  if (!postedAt) return 'Recently posted'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(new Date(postedAt))
}

export default function AnnouncementList({ announcements }) {
  if (!announcements.length) {
    return <div className="empty-card">No recent announcements right now.</div>
  }

  return (
    <div className="deadlines announcements rise">
      {announcements.map((announcement) => (
        <a
          className="announcement-item"
          href={announcement.url || '#'}
          key={`${announcement.course_id}-${announcement.title}-${announcement.posted_at || 'na'}`}
          rel="noreferrer"
          target={announcement.url ? '_blank' : undefined}
        >
          <div className="announcement-code">{displayCourseCode(announcement.course_code)}</div>
          <div className="announcement-body">
            <div className="announcement-title">{announcement.title}</div>
            <div className="announcement-preview">{announcement.preview || 'Open in Quercus to read the full announcement.'}</div>
          </div>
          <div className="announcement-date">{formatPosted(announcement.posted_at)}</div>
        </a>
      ))}
    </div>
  )
}
