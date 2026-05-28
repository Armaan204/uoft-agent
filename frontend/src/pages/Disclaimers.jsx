import { Link } from 'react-router-dom'

export default function Disclaimers() {
  return (
    <div className="legal-page">
      <header className="legal-header">
        <Link to="/" className="legal-brand">UofT Agent</Link>
        <nav className="legal-nav">
          <Link to="/privacy" className="legal-nav-link">Privacy Policy</Link>
          <Link to="/terms" className="legal-nav-link">Terms of Use</Link>
        </nav>
      </header>

      <h1 className="legal-h1">Disclaimers</h1>
      <p className="legal-updated">Last updated: May 22, 2026</p>

      <section className="legal-section">
        <h2 className="legal-h2">Non-Affiliation with the University of Toronto</h2>
        <p className="legal-p">
          UofT Agent is an independent student project and is not affiliated with, endorsed by, or
          officially connected to the University of Toronto or any of its campuses, faculties,
          divisions, or administrative units. The University of Toronto has not reviewed or approved
          UofT Agent and bears no responsibility for its content or functionality.
        </p>
        <p className="legal-p">
          Official UofT academic resources, including your degree audit, enrollment tools, and
          academic history, are available at{' '}
          <a href="https://acorn.utoronto.ca" target="_blank" rel="noopener noreferrer" className="legal-a">
            acorn.utoronto.ca
          </a>.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">AI Responses</h2>
        <p className="legal-p">
          UofT Agent is powered by Claude, an AI assistant developed by{' '}
          <a href="https://www.anthropic.com" target="_blank" rel="noopener noreferrer" className="legal-a">
            Anthropic
          </a>. AI-generated responses may contain errors, hallucinations, outdated information, or
          statements that are incomplete or misleading. The AI assistant has no access to real-time
          UofT systems beyond what is imported into UofT Agent.
        </p>
        <p className="legal-p">
          UofT Agent responses are not a substitute for official academic advice from your
          professor, academic advisor, registrar, or program coordinator. Always verify important
          academic information — including course requirements, enrollment decisions, and graduation
          eligibility — with official UofT sources.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">Degree Planner</h2>
        <p className="legal-p">
          The Degree Planner feature is a planning aid only and does not constitute an official
          degree audit. Program requirements shown may not be fully accurate, complete, or current.
          Requirement data is extracted from the UofT academic calendar using automated tools and
          may contain errors or omissions.
        </p>
        <p className="legal-p">
          Always confirm your graduation progress with the official{' '}
          <a
            href="https://acorn.utoronto.ca/sws/#/progress/undergraduate/auditDegree"
            target="_blank"
            rel="noopener noreferrer"
            className="legal-a"
          >
            Degree Explorer on ACORN
          </a>{' '}
          and consult your academic registrar before making enrollment or graduation decisions.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">Grade Calculations and Cached Data</h2>
        <p className="legal-p">
          Grade and course data displayed in UofT Agent may be up to several hours old depending on
          cache state. The app serves cached data first and refreshes in the background. Data shown
          does not reflect real-time Canvas state and may not include recent grade updates, late
          submissions, or instructor adjustments.
        </p>
        <p className="legal-p">
          Weighted averages and GPA estimates are computed from Quercus data, which may be
          incomplete, delayed, or subject to change. Calculations are for informational purposes
          only. Final grades and academic standing are determined solely by the University of
          Toronto. Do not rely on UofT Agent grade estimates for any official academic standing
          decision.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">Quercus Integration</h2>
        <p className="legal-p">
          UofT Agent accesses your course and grade data via your Quercus personal access token.
          Changes to the Quercus (Canvas) platform made by the University of Toronto or by
          Instructure (the makers of Canvas) may affect UofT Agent's functionality at any time
          without notice. UofT Agent is not affiliated with or endorsed by Instructure.
        </p>
        <p className="legal-p">
          If UofT Agent loses access to your Quercus data unexpectedly, your token may have
          expired or been revoked. You can reconnect from the app settings or generate a new token
          in Canvas under Account → Settings → New Access Token.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">Chrome Extension</h2>
        <p className="legal-p">
          The UofT Agent Chrome extension transmits your ACORN academic history to UofT Agent
          servers over HTTPS. This data leaves your device and is stored in our database. Do not
          use the extension on shared or public devices.
        </p>
        <p className="legal-p">
          The extension runs only on{' '}
          <code style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>acorn.utoronto.ca</code>{' '}
          and only after you manually click the import button. It does not collect passwords, does
          not automate login, and does not run on any other websites. For further details, see the{' '}
          <a
            href="https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa"
            target="_blank"
            rel="noopener noreferrer"
            className="legal-a"
          >
            extension listing
          </a>{' '}
          on the Chrome Web Store.
        </p>
      </section>

      <footer className="legal-page-footer">
        <span>© 2026 UofT Agent</span>
        <div className="legal-footer-links">
          <Link to="/privacy" className="legal-footer-link">Privacy Policy</Link>
          <Link to="/terms" className="legal-footer-link">Terms of Use</Link>
          <a href="mailto:uoftagent@gmail.com" className="legal-footer-link">Contact</a>
        </div>
      </footer>
    </div>
  )
}
