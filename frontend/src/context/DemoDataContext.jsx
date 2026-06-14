import { createContext, useContext } from 'react'
import {
  MOCK_COURSES,
  MOCK_ANNOUNCEMENTS,
  MOCK_COURSE_GRADES,
  MOCK_ACORN,
  MOCK_DEGREE_PLANNER,
  MOCK_CHAT_RESPONSES,
} from '../data/mockData'

const DemoDataContext = createContext(null)

export function DemoDataProvider({ children }) {
  const value = {
    courses: MOCK_COURSES,
    announcements: MOCK_ANNOUNCEMENTS,
    courseGrades: MOCK_COURSE_GRADES,
    acorn: MOCK_ACORN,
    degreePlanner: MOCK_DEGREE_PLANNER,
    chatResponses: MOCK_CHAT_RESPONSES,
  }

  return (
    <DemoDataContext.Provider value={value}>
      {children}
    </DemoDataContext.Provider>
  )
}

export function useDemoData() {
  const context = useContext(DemoDataContext)
  if (!context) throw new Error('useDemoData must be used within DemoDataProvider')
  return context
}
