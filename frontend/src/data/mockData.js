const today = new Date()
const inDays = (n) => new Date(today.getTime() + n * 86400000).toISOString()
const daysAgo = (n) => new Date(today.getTime() - n * 86400000).toISOString()

export const MOCK_COURSES = [
  {
    id: 'demo-1',
    course_code: 'CSCA08H3',
    name: 'CSCA08H3: Introduction to Computer Science I',
    current_grade: 78.4,
    display_grade: 78.4,
    letter_grade: 'B+',
    risk_flag: 'On track',
    term_name: 'Fall 2025',
    deadlines: [
      { course_code: 'CSCA08H3', name: 'Assignment 4: Recursion', due_at: inDays(5) },
    ],
  },
  {
    id: 'demo-2',
    course_code: 'STAB22H3',
    name: 'STAB22H3: Statistics I',
    current_grade: 84.1,
    display_grade: 84.1,
    letter_grade: 'A-',
    risk_flag: 'Safe',
    term_name: 'Fall 2025',
    deadlines: [
      { course_code: 'STAB22H3', name: 'Problem Set 6', due_at: inDays(3) },
    ],
  },
  {
    id: 'demo-3',
    course_code: 'ENGB06H3',
    name: 'ENGB06H3: English Literature',
    current_grade: 71.2,
    display_grade: 71.2,
    letter_grade: 'B-',
    risk_flag: 'At risk',
    term_name: 'Fall 2025',
    deadlines: [
      { course_code: 'ENGB06H3', name: 'Essay 3: Modernism', due_at: inDays(10) },
    ],
  },
  {
    id: 'demo-4',
    course_code: 'MGTA01H3',
    name: 'MGTA01H3: Introduction to Management',
    current_grade: 88.9,
    display_grade: 88.9,
    letter_grade: 'A',
    risk_flag: 'Safe',
    term_name: 'Fall 2025',
    deadlines: [
      { course_code: 'MGTA01H3', name: 'Group Case Analysis', due_at: inDays(8) },
    ],
  },
]

export const MOCK_ANNOUNCEMENTS = [
  {
    course_id: 'demo-1',
    course_code: 'CSCA08H3',
    title: 'Midterm Grades Posted',
    preview: 'Midterm grades are now available on Quercus. Please review your results.',
    posted_at: daysAgo(2),
  },
  {
    course_id: 'demo-2',
    course_code: 'STAB22H3',
    title: 'Office Hours Changed This Week',
    preview: 'Due to the holiday Monday, office hours are moved to Wednesday 2-4pm.',
    posted_at: daysAgo(1),
  },
]

export const MOCK_COURSE_GRADES = {
  'demo-1': {
    grade: { weighted_grade: 78.4 },
    component_model: {
      components: [
        { component_key: 'assignments', name: 'Assignments', weight: 30, status: 'graded', pct: 82, earned: 82, possible: 100 },
        { component_key: 'midterm', name: 'Midterm', weight: 25, status: 'graded', pct: 74, earned: 74, possible: 100 },
        { component_key: 'labs', name: 'Labs', weight: 10, status: 'graded', pct: 91, earned: 91, possible: 100 },
        { component_key: 'final', name: 'Final Exam', weight: 35, status: 'ungraded', pct: null, earned: null, possible: 100 },
      ],
      assignments_by_component: {
        assignments: [
          { assignment_id: 'a1', name: 'Assignment 1', status: 'graded', earned: 85, possible: 100, pct: 85 },
          { assignment_id: 'a2', name: 'Assignment 2', status: 'graded', earned: 79, possible: 100, pct: 79 },
          { assignment_id: 'a3', name: 'Assignment 3', status: 'graded', earned: 82, possible: 100, pct: 82 },
        ],
        midterm: [
          { assignment_id: 'mt', name: 'Midterm Exam', status: 'graded', earned: 74, possible: 100, pct: 74 },
        ],
        labs: [
          { assignment_id: 'l1', name: 'Lab 1', status: 'graded', earned: 90, possible: 100, pct: 90 },
          { assignment_id: 'l2', name: 'Lab 2', status: 'graded', earned: 92, possible: 100, pct: 92 },
        ],
      },
    },
    live_components: [],
  },
  'demo-2': {
    grade: { weighted_grade: 84.1 },
    component_model: {
      components: [
        { component_key: 'problem-sets', name: 'Problem Sets', weight: 25, status: 'graded', pct: 88, earned: 88, possible: 100 },
        { component_key: 'midterm', name: 'Midterm', weight: 30, status: 'graded', pct: 81, earned: 81, possible: 100 },
        { component_key: 'tutorials', name: 'Tutorial Quizzes', weight: 10, status: 'graded', pct: 95, earned: 95, possible: 100 },
        { component_key: 'final', name: 'Final Exam', weight: 35, status: 'ungraded', pct: null, earned: null, possible: 100 },
      ],
      assignments_by_component: {
        'problem-sets': [
          { assignment_id: 'ps1', name: 'Problem Set 1', status: 'graded', earned: 90, possible: 100, pct: 90 },
          { assignment_id: 'ps2', name: 'Problem Set 2', status: 'graded', earned: 85, possible: 100, pct: 85 },
          { assignment_id: 'ps3', name: 'Problem Set 3', status: 'graded', earned: 89, possible: 100, pct: 89 },
        ],
        midterm: [
          { assignment_id: 'mt', name: 'Midterm Exam', status: 'graded', earned: 81, possible: 100, pct: 81 },
        ],
        tutorials: [
          { assignment_id: 'tq1', name: 'Quiz 1', status: 'graded', earned: 93, possible: 100, pct: 93 },
          { assignment_id: 'tq2', name: 'Quiz 2', status: 'graded', earned: 97, possible: 100, pct: 97 },
        ],
      },
    },
    live_components: [],
  },
  'demo-3': {
    grade: { weighted_grade: 71.2 },
    component_model: {
      components: [
        { component_key: 'essays', name: 'Essays', weight: 40, status: 'graded', pct: 69, earned: 69, possible: 100 },
        { component_key: 'participation', name: 'Participation', weight: 15, status: 'graded', pct: 80, earned: 80, possible: 100 },
        { component_key: 'midterm', name: 'Midterm Paper', weight: 20, status: 'graded', pct: 72, earned: 72, possible: 100 },
        { component_key: 'final', name: 'Final Essay', weight: 25, status: 'ungraded', pct: null, earned: null, possible: 100 },
      ],
      assignments_by_component: {
        essays: [
          { assignment_id: 'e1', name: 'Essay 1: Romanticism', status: 'graded', earned: 65, possible: 100, pct: 65 },
          { assignment_id: 'e2', name: 'Essay 2: Victorian Lit', status: 'graded', earned: 73, possible: 100, pct: 73 },
        ],
        participation: [
          { assignment_id: 'p1', name: 'Participation', status: 'graded', earned: 80, possible: 100, pct: 80 },
        ],
        midterm: [
          { assignment_id: 'mp', name: 'Midterm Paper', status: 'graded', earned: 72, possible: 100, pct: 72 },
        ],
      },
    },
    live_components: [],
  },
  'demo-4': {
    grade: { weighted_grade: 88.9 },
    component_model: {
      components: [
        { component_key: 'case-studies', name: 'Case Studies', weight: 30, status: 'graded', pct: 91, earned: 91, possible: 100 },
        { component_key: 'midterm', name: 'Midterm', weight: 25, status: 'graded', pct: 85, earned: 85, possible: 100 },
        { component_key: 'group-project', name: 'Group Project', weight: 20, status: 'graded', pct: 93, earned: 93, possible: 100 },
        { component_key: 'final', name: 'Final Exam', weight: 25, status: 'ungraded', pct: null, earned: null, possible: 100 },
      ],
      assignments_by_component: {
        'case-studies': [
          { assignment_id: 'cs1', name: 'Case Study 1', status: 'graded', earned: 89, possible: 100, pct: 89 },
          { assignment_id: 'cs2', name: 'Case Study 2', status: 'graded', earned: 93, possible: 100, pct: 93 },
        ],
        midterm: [
          { assignment_id: 'mt', name: 'Midterm Exam', status: 'graded', earned: 85, possible: 100, pct: 85 },
        ],
        'group-project': [
          { assignment_id: 'gp', name: 'Group Project', status: 'graded', earned: 93, possible: 100, pct: 93 },
        ],
      },
    },
    live_components: [],
  },
}

export const MOCK_ACORN = {
  importedAt: daysAgo(14),
  programs: [
    {
      programName: 'Computer Science (Science) Specialist Co-op',
      enrollmentStatus: 'Invited',
      institution: 'University of Toronto Scarborough',
      enrollmentPeriod: '2023-2028',
      startSession: 'Fall 2023',
    },
  ],
  terms: [
    { term: 'Fall 2023', sessionalGpa: 3.1, cumulativeGpa: 3.1 },
    { term: 'Winter 2024', sessionalGpa: 3.4, cumulativeGpa: 3.23 },
    { term: 'Fall 2024', sessionalGpa: 3.2, cumulativeGpa: 3.23 },
  ],
  courses: [
    { courseCode: 'CSCA08H3', title: 'Intro to Computer Science I', term: 'Fall 2023', credits: '0.50', mark: '75', grade: 'B', courseAverage: '68' },
    { courseCode: 'CSCA48H3', title: 'Intro to Computer Science II', term: 'Winter 2024', credits: '0.50', mark: '81', grade: 'A-', courseAverage: '65' },
    { courseCode: 'MATA31H3', title: 'Calculus I for Math Sciences', term: 'Fall 2023', credits: '0.50', mark: '72', grade: 'B', courseAverage: '61' },
    { courseCode: 'MATA37H3', title: 'Calculus II for Math Sciences', term: 'Winter 2024', credits: '0.50', mark: '78', grade: 'B+', courseAverage: '58' },
    { courseCode: 'STAB22H3', title: 'Statistics I', term: 'Fall 2023', credits: '0.50', mark: '83', grade: 'A-', courseAverage: '72' },
    { courseCode: 'CSCA67H3', title: 'Discrete Mathematics', term: 'Winter 2024', credits: '0.50', mark: '80', grade: 'A-', courseAverage: '63' },
    { courseCode: 'CSCB07H3', title: 'Software Design', term: 'Fall 2024', credits: '0.50', mark: '77', grade: 'B+', courseAverage: '70' },
    { courseCode: 'CSCB09H3', title: 'Software Tools & Systems', term: 'Fall 2024', credits: '0.50', mark: '82', grade: 'A-', courseAverage: '67' },
  ],
}

export const MOCK_DEGREE_PLANNER = [
  {
    program_name: 'Computer Science (Science) Specialist Co-op',
    academic_year: '2023-2028',
    program_credits_required: 20.0,
    credits_satisfied: 4.0,
    credits_in_progress: 2.0,
    is_coop: true,
    groups: [
      {
        id: 'core-1',
        section: 'core',
        label: 'First Year Courses',
        status: 'satisfied',
        credits_satisfied: 3.0,
        credits_required: 3.0,
        items: [
          { id: 'r1', type: 'required', label: 'CSCA08H3', status: 'satisfied', credits: 0.5, satisfied_by: ['CSCA08H3'] },
          { id: 'r2', type: 'required', label: 'CSCA48H3', status: 'satisfied', credits: 0.5, satisfied_by: ['CSCA48H3'] },
          { id: 'r3', type: 'required', label: 'CSCA67H3', status: 'satisfied', credits: 0.5, satisfied_by: ['CSCA67H3'] },
          { id: 'r4', type: 'required', label: 'MATA31H3', status: 'satisfied', credits: 0.5, satisfied_by: ['MATA31H3'] },
          { id: 'r5', type: 'required', label: 'MATA37H3', status: 'satisfied', credits: 0.5, satisfied_by: ['MATA37H3'] },
          { id: 'r6', type: 'required', label: 'STAB22H3', status: 'satisfied', credits: 0.5, satisfied_by: ['STAB22H3'] },
        ],
      },
      {
        id: 'core-2',
        section: 'core',
        label: 'Second Year Courses',
        status: 'in_progress',
        credits_satisfied: 1.0,
        credits_required: 2.5,
        items: [
          { id: 'r7', type: 'required', label: 'CSCB07H3', status: 'satisfied', credits: 0.5, satisfied_by: ['CSCB07H3'] },
          { id: 'r8', type: 'required', label: 'CSCB09H3', status: 'satisfied', credits: 0.5, satisfied_by: ['CSCB09H3'] },
          { id: 'r9', type: 'required', label: 'CSCB36H3', status: 'in_progress', credits: 0.5, in_progress_by: ['CSCB36H3'] },
          { id: 'r10', type: 'required', label: 'CSCB63H3', status: 'in_progress', credits: 0.5, in_progress_by: ['CSCB63H3'] },
          { id: 'r11', type: 'required', label: 'MATA22H3', status: 'remaining', credits: 0.5, courses_needed: ['MATA22H3'] },
        ],
      },
      {
        id: 'core-3',
        section: 'core',
        label: 'Upper Year Required',
        status: 'remaining',
        credits_satisfied: 0,
        credits_required: 3.5,
        items: [
          { id: 'r12', type: 'required', label: 'CSCC01H3', status: 'remaining', credits: 0.5, courses_needed: ['CSCC01H3'] },
          { id: 'r13', type: 'required', label: 'CSCC09H3', status: 'remaining', credits: 0.5, courses_needed: ['CSCC09H3'] },
          { id: 'r14', type: 'required', label: 'CSCC43H3', status: 'remaining', credits: 0.5, courses_needed: ['CSCC43H3'] },
          { id: 'r15', type: 'required', label: 'CSCC69H3', status: 'remaining', credits: 0.5, courses_needed: ['CSCC69H3'] },
          { id: 'r16', type: 'required', label: 'CSCD01H3 or CSCD03H3', status: 'remaining', credits: 0.5, courses_needed: ['CSCD01H3', 'CSCD03H3'] },
          { id: 'r17', type: 'required', label: 'MATB24H3', status: 'remaining', credits: 0.5, courses_needed: ['MATB24H3'] },
          { id: 'r18', type: 'required', label: 'STAB52H3', status: 'remaining', credits: 0.5, courses_needed: ['STAB52H3'] },
        ],
      },
      {
        id: 'stream-1',
        section: 'stream',
        label: 'C-level CS Electives',
        status: 'in_progress',
        credits_satisfied: 0,
        credits_required: 1.5,
        items: [
          {
            id: 'r19',
            type: 'n_credits_from_list',
            label: '1.5 credits from C-level CSCC courses',
            status: 'in_progress',
            credits_needed: 1.5,
            credits_satisfied: 0,
            in_progress_by: ['CSCC11H3', 'CSCC37H3'],
            courses: ['CSCC11H3', 'CSCC37H3', 'CSCC63H3', 'CSCC73H3'],
          },
        ],
      },
      {
        id: 'stream-2',
        section: 'stream',
        label: 'D-level CS Electives',
        status: 'remaining',
        credits_satisfied: 0,
        credits_required: 1.0,
        items: [
          {
            id: 'r20',
            type: 'open_pool',
            label: '1.0 credits from D-level CSC courses',
            status: 'remaining',
            credits_needed: 1.0,
            credits_satisfied: 0,
          },
        ],
      },
    ],
    coop: {
      work_terms_status: 'in_progress',
      work_terms_completed: 1,
      work_terms_required: 3,
      preparation: [
        { id: 'coop1', type: 'required', label: 'COPB50H3', status: 'satisfied', credits: 0, satisfied_by: ['COPB50H3'] },
      ],
      search_courses: [
        { id: 'coop2', type: 'required', label: 'COPC98H3', status: 'satisfied', credits: 0, satisfied_by: ['COPC98H3'] },
        { id: 'coop3', type: 'required', label: 'COPC99H3', status: 'in_progress', credits: 0, in_progress_by: ['COPC99H3'] },
      ],
      work_term_courses: [
        { id: 'coop4', type: 'required', label: 'Work Term 1', status: 'satisfied', credits: 0, satisfied_by: ['COPD01Y3'] },
        { id: 'coop5', type: 'required', label: 'Work Term 2', status: 'remaining', credits: 0, courses_needed: ['COPD03Y3'] },
        { id: 'coop6', type: 'required', label: 'Work Term 3', status: 'remaining', credits: 0, courses_needed: ['COPD11Y3'] },
      ],
    },
  },
]

export const MOCK_CHAT_RESPONSES = {
  "What's my current GPA?": `Based on your current grades this semester, here's your standing:

| Course | Grade | Letter |
|--------|-------|--------|
| CSCA08H3 | 78.4% | B+ |
| STAB22H3 | 84.1% | A- |
| ENGB06H3 | 71.2% | B- |
| MGTA01H3 | 88.9% | A |

Your estimated semester GPA is **3.18** (using UofT's 4.0 scale). Your strongest course is MGTA01 and your lowest is ENGB06.`,

  "What do I need on my CSCA08 final?": `Your CSCA08H3 final exam is worth **35%** of your total grade. Here's what you'd need to hit each letter grade:

- **A+ (90%)**: You'd need **99%** on the final — very difficult given current standing
- **A (85%)**: You'd need **85%** on the final
- **A- (80%)**: You'd need **71%** on the final — very achievable
- **B+ (77%)**: You'd need **62%** on the final — you're already close

Your current standing before the final is **78.4%** (based on 65% of coursework completed). Focus on the recursion and object-oriented topics that were weaker on the midterm.`,

  "When is my next deadline?": `Here are your upcoming deadlines:

1. **STAB22H3 — Problem Set 6** — due in 3 days
2. **CSCA08H3 — Assignment 4: Recursion** — due in 5 days
3. **MGTA01H3 — Group Case Analysis** — due in 8 days
4. **ENGB06H3 — Essay 3: Modernism** — due in 10 days

Your most urgent one is the STAB22 problem set. Would you like tips on managing these deadlines?`,

  "Am I on track to graduate?": `Based on your ACORN history and current enrollment, here's your degree progress for **Computer Science (Science) Specialist Co-op**:

**Completed:** 4.0 / 20.0 credits (20%)
**In Progress:** 2.0 credits

You're on track for your year. Key milestones coming up:
- Complete MATA22H3 (Linear Algebra) — prerequisite for many upper-year courses
- Maintain GPA above 2.5 to stay in the co-op program
- You've completed 1 of 3 required work terms

At your current pace, estimated graduation is **April 2028**. You're meeting all first and second year requirements on schedule.`,
}
