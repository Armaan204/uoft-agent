import { Link } from 'react-router-dom'

export default function PrivacyPolicy() {
  return (
    <div className="legal-page">
      <header className="legal-header">
        <Link to="/" className="legal-brand">UofT Agent</Link>
        <nav className="legal-nav">
          <Link to="/terms" className="legal-nav-link">Terms of Use</Link>
          <Link to="/disclaimers" className="legal-nav-link">Disclaimers</Link>
        </nav>
      </header>

      <h1 className="legal-h1">Privacy Policy</h1>
      <p className="legal-updated">Last updated: May 22, 2026</p>

      <section className="legal-section">
        <h2 className="legal-h2">1. What We Collect</h2>
        <p className="legal-p">When you use UofT Agent, we may collect the following information:</p>
        <ul className="legal-ul">
          <li className="legal-li">
            <strong>Google account information</strong> — your name, email address, and profile
            picture provided via Google OAuth when you sign in.
          </li>
          <li className="legal-li">
            <strong>Quercus personal access token</strong> — the API token you provide to connect
            your Quercus (Canvas) account. This token is encrypted with Fernet symmetric encryption
            before being stored.
          </li>
          <li className="legal-li">
            <strong>ACORN academic history</strong> — course codes, titles, credits, marks, grades,
            and term information imported via the UofT Agent Chrome extension.
          </li>
          <li className="legal-li">
            <strong>Chat messages and conversation history</strong> — your messages to the AI
            assistant and the responses generated.
          </li>
          <li className="legal-li">
            <strong>Grade overrides and manual entries</strong> — adjustments you make to grade
            calculations within the app.
          </li>
          <li className="legal-li">
            <strong>Rate limiting logs</strong> — user ID and request timestamps used to enforce
            usage limits, retained on a rolling 30-day basis.
          </li>
          <li className="legal-li">
            <strong>Session tokens</strong> — JWT tokens stored in your browser for authentication.
            These tokens expire and are used solely to maintain your active session.
          </li>
        </ul>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">2. How We Use Your Information</h2>
        <ul className="legal-ul">
          <li className="legal-li">Authenticate you and maintain your session via email/password, Google OAuth, and signed JWT tokens.</li>
          <li className="legal-li">Fetch your course and grade data from Quercus on your behalf using your stored token.</li>
          <li className="legal-li">Generate AI-powered responses to your academic questions (see Section 3).</li>
          <li className="legal-li">Display your ACORN academic history and compute graduation progress estimates.</li>
          <li className="legal-li">Enforce usage limits and maintain service security.</li>
        </ul>
        <p className="legal-p">
          We do not sell, rent, or share your data for advertising purposes. Your data is used only
          to operate and improve UofT Agent.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">3. Third Parties</h2>
        <ul className="legal-ul">
          <li className="legal-li">
            <strong>Google OAuth</strong> — used for sign-in. Google may collect data per their{' '}
            <a
              href="https://policies.google.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="legal-a"
            >
              Privacy Policy
            </a>.
          </li>
          <li className="legal-li">
            <strong>Anthropic API</strong> — when you use the AI assistant, both your chat messages
            and relevant course and grade context are sent to Anthropic to generate responses. This
            means your academic data (course names, grades, assignments) may be included in requests
            to Anthropic, not just the text of your chat messages alone. Anthropic does not use API
            data to train their models by default. See{' '}
            <a
              href="https://www.anthropic.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="legal-a"
            >
              anthropic.com/privacy
            </a>{' '}
            for full details on their data handling.
          </li>
          <li className="legal-li">
            <strong>Supabase (EU West)</strong> — stores your account information, encrypted
            Quercus token, ACORN academic history, grade snapshots, and chat history.
          </li>
          <li className="legal-li">
            <strong>Railway (EU West)</strong> — hosts the UofT Agent backend application.
          </li>
        </ul>
        <p className="legal-p">All data is hosted in the European Union. We do not host data in the United States.</p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">4. Operator Access</h2>
        <p className="legal-p">
          The service operator (sole developer) may access stored account data for operational
          purposes including debugging, incident response, and support. If you request support and
          ask the operator to review your account, they may do so. All such access is logged.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">5. Chrome Extension Data Transmission</h2>
        <p className="legal-p">
          The UofT Agent Chrome extension transmits your ACORN academic history to UofT Agent
          servers over HTTPS when you click Import Academic History. This data leaves your device
          and is stored in our database. The data transmitted includes course codes, titles,
          credits, marks, grades, and term information.
        </p>
        <p className="legal-p">
          The extension does not collect passwords, does not automate login, and only operates on{' '}
          <code style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>acorn.utoronto.ca</code>.
          Imports are always manually triggered. Do not use the extension on shared or public
          devices. For further details, see the extension listing on the{' '}
          <a
            href="https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa"
            target="_blank"
            rel="noopener noreferrer"
            className="legal-a"
          >
            Chrome Web Store
          </a>.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">6. Retention Periods</h2>
        <ul className="legal-ul">
          <li className="legal-li"><strong>Chat history</strong> — retained until you request account deletion.</li>
          <li className="legal-li"><strong>Grade snapshots and course data</strong> — retained until you request account deletion.</li>
          <li className="legal-li"><strong>Quercus API token</strong> — retained until you revoke it within the app or request account deletion.</li>
          <li className="legal-li"><strong>Rate limiting logs</strong> (user ID and request timestamps) — 30-day rolling basis.</li>
          <li className="legal-li"><strong>Usage and device data</strong> — retained for internal purposes for up to 90 days.</li>
        </ul>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">7. Data Deletion</h2>
        <p className="legal-p">
          To request deletion of your account and all associated data, email{' '}
          <a href="mailto:uoftagent@gmail.com" className="legal-a">
            uoftagent@gmail.com
          </a>{' '}
          with the subject line <strong>"Data Deletion Request"</strong>. Requests will be
          processed within 30 days.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">8. Security</h2>
        <ul className="legal-ul">
          <li className="legal-li">Quercus tokens are encrypted with Fernet symmetric encryption before storage.</li>
          <li className="legal-li">All data in transit is protected with HTTPS.</li>
          <li className="legal-li">Email/password authentication is handled by Supabase Auth; raw passwords are not stored in UofT Agent tables.</li>
          <li className="legal-li">Session management uses signed JWT tokens with expiry.</li>
        </ul>
        <p className="legal-p">
          No security measure is infallible. We make reasonable efforts to protect your data but
          cannot guarantee absolute security against all threats.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">9. Your Rights (PIPEDA)</h2>
        <p className="legal-p">
          Under Canada's Personal Information Protection and Electronic Documents Act (PIPEDA) and
          applicable Ontario privacy law, you have the right to:
        </p>
        <ul className="legal-ul">
          <li className="legal-li">Access the personal information we hold about you.</li>
          <li className="legal-li">Request corrections to inaccurate or incomplete information.</li>
          <li className="legal-li">Withdraw consent, subject to legal and contractual restrictions.</li>
          <li className="legal-li">Request deletion of your data (see Section 7).</li>
        </ul>
        <p className="legal-p">
          To exercise these rights, contact{' '}
          <a href="mailto:uoftagent@gmail.com" className="legal-a">
            uoftagent@gmail.com
          </a>.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">10. Children</h2>
        <p className="legal-p">
          UofT Agent is not intended for users under the age of 13. We do not knowingly collect
          personal information from children under 13. If you believe a child has provided us with
          their information, contact us and we will take steps to remove it promptly.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">11. Policy Updates</h2>
        <p className="legal-p">
          We may update this policy from time to time. The "Last updated" date at the top of this
          page reflects the most recent revision. Continued use of UofT Agent after changes
          constitutes acceptance of the updated policy.
        </p>
        <p className="legal-p">
          Questions about this policy?{' '}
          <a href="mailto:uoftagent@gmail.com" className="legal-a">
            uoftagent@gmail.com
          </a>
        </p>
      </section>

      <footer className="legal-page-footer">
        <span>© 2026 UofT Agent</span>
        <div className="legal-footer-links">
          <Link to="/terms" className="legal-footer-link">Terms of Use</Link>
          <Link to="/disclaimers" className="legal-footer-link">Disclaimers</Link>
          <a href="mailto:uoftagent@gmail.com" className="legal-footer-link">Contact</a>
        </div>
      </footer>
    </div>
  )
}
