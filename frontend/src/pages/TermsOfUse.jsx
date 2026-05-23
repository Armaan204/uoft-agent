import { Link } from 'react-router-dom'

export default function TermsOfUse() {
  return (
    <div className="legal-page">
      <header className="legal-header">
        <Link to="/" className="legal-brand">UofT Agent</Link>
        <nav className="legal-nav">
          <Link to="/privacy" className="legal-nav-link">Privacy Policy</Link>
          <Link to="/disclaimers" className="legal-nav-link">Disclaimers</Link>
        </nav>
      </header>

      <h1 className="legal-h1">Terms of Use</h1>
      <p className="legal-updated">Last updated: May 22, 2026</p>

      <section className="legal-section">
        <h2 className="legal-h2">1. Agreement to Terms</h2>
        <p className="legal-p">
          By accessing and using UofT Agent at uoft-agent.com, you agree to be bound by these
          Terms of Use and our{' '}
          <Link to="/privacy" className="legal-a">Privacy Policy</Link>. If you do not agree
          to these terms, do not use the service.
        </p>
        <p className="legal-p">
          We reserve the right to modify these terms at any time. The "Last updated" date above
          reflects the most recent revision. Continued use of UofT Agent after changes constitutes
          acceptance of the updated terms.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">2. Not an Official UofT Tool</h2>
        <p className="legal-p">
          UofT Agent is an independent student project and is not affiliated with, endorsed by, or
          officially connected to the University of Toronto or any of its faculties, divisions, or
          administrative units. The University of Toronto has not reviewed, approved, or sponsored
          UofT Agent in any way and is not responsible for its content, accuracy, or availability.
        </p>
        <p className="legal-p">
          The official UofT student portal and academic resources are available at{' '}
          <a href="https://acorn.utoronto.ca" target="_blank" rel="noopener noreferrer" className="legal-a">
            acorn.utoronto.ca
          </a>{' '}
          and{' '}
          <a href="https://utoronto.ca" target="_blank" rel="noopener noreferrer" className="legal-a">
            utoronto.ca
          </a>.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">3. User Representations</h2>
        <p className="legal-p">By using UofT Agent, you represent that:</p>
        <ul className="legal-ul">
          <li className="legal-li">You are at least 13 years of age.</li>
          <li className="legal-li">All information you provide is accurate and complete.</li>
          <li className="legal-li">You have the legal capacity to agree to these terms.</li>
          <li className="legal-li">You will not use the service for any unlawful or unauthorized purpose.</li>
          <li className="legal-li">Your use of the service will not violate any applicable law or regulation.</li>
        </ul>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">4. Prohibited Activities</h2>
        <p className="legal-p">You may not:</p>
        <ul className="legal-ul">
          <li className="legal-li">Systematically scrape, harvest, or collect data from the service.</li>
          <li className="legal-li">Use automated scripts, bots, or other non-human means to interact with the service.</li>
          <li className="legal-li">Share your account credentials with other persons.</li>
          <li className="legal-li">Attempt to reverse engineer, decompile, or disassemble any part of the service.</li>
          <li className="legal-li">Interfere with the security, availability, or integrity of the service or its infrastructure.</li>
          <li className="legal-li">Use the service in a manner intended to harm, defraud, or exploit others.</li>
          <li className="legal-li">Attempt to circumvent rate limiting, authentication, or other access controls.</li>
        </ul>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">5. Quercus Token Authorization and Revocation</h2>
        <p className="legal-p">
          By providing your Quercus personal access token, you authorize UofT Agent to access your
          Canvas course and grade data on your behalf. You are responsible for the confidentiality
          of your token and for any activity that occurs through it.
        </p>
        <div className="legal-callout">
          <strong>Important — Revoking Access:</strong> To fully revoke UofT Agent's access to your
          Quercus data, you must delete your personal access token directly in Canvas. Log in to{' '}
          <a href="https://quercus.utoronto.ca" target="_blank" rel="noopener noreferrer" className="legal-a">
            quercus.utoronto.ca
          </a>{' '}
          → Account → Settings → Approved Integrations, and delete the token there. Removing the
          token from the UofT Agent settings page alone does not revoke Canvas-level access.
        </div>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">6. UofT Acceptable Use</h2>
        <p className="legal-p">
          By providing your Quercus personal access token, you confirm that your use complies with
          the University of Toronto's acceptable use policies. UofT Agent is not responsible for any
          policy violations arising from your use of your own token with third-party tools.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">7. AI-Generated Content</h2>
        <p className="legal-p">
          UofT Agent uses Claude, an AI assistant developed by Anthropic, to generate responses to
          your questions. AI-generated responses may contain errors, hallucinations, or information
          that is outdated, incomplete, or inaccurate.
        </p>
        <p className="legal-p">
          Do not make enrollment, graduation, course selection, or other academic decisions based
          solely on agent output. Always verify important information with official UofT sources,
          your instructor, academic advisor, or registrar.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">8. Beta / Active Development</h2>
        <p className="legal-p">
          UofT Agent is under active development. Features may be added, changed, or removed at any
          time without notice. The service is provided in its current state and does not carry any
          implied commitment to future functionality, availability, or feature parity.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">9. Modifications and Interruptions</h2>
        <p className="legal-p">
          We reserve the right to modify, suspend, or discontinue the service at any time and for
          any reason without notice. We are not liable for any loss, damage, or inconvenience caused
          by interruptions, delays, or errors in service availability.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">10. Disclaimer of Warranties</h2>
        <p className="legal-caps">
          The service is provided "as is" and "as available" without warranties of any kind, express
          or implied, including but not limited to warranties of merchantability, fitness for a
          particular purpose, or non-infringement. We do not warrant that the service will be
          uninterrupted, error-free, or that any defects will be corrected. We do not warrant the
          accuracy, completeness, or reliability of any content or information provided through the
          service.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">11. Limitation of Liability</h2>
        <p className="legal-p">
          To the maximum extent permitted by applicable law in the Province of Ontario, our
          liability to you for any cause whatsoever, and regardless of the form of the action, shall
          be limited to the fullest extent the law allows. We are not liable for indirect,
          incidental, consequential, special, or punitive damages of any kind arising from your use
          of, or inability to use, the service.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">12. Indemnification</h2>
        <p className="legal-p">
          You agree to defend, indemnify, and hold harmless UofT Agent and its developer from any
          claims, liabilities, damages, losses, and expenses (including reasonable legal fees)
          arising from your use of the service, your breach of these terms, or your violation of
          any third party's rights.
        </p>
      </section>

      <section className="legal-section">
        <h2 className="legal-h2">13. Governing Law</h2>
        <p className="legal-p">
          These Terms of Use are governed by and construed in accordance with the laws of the
          Province of Ontario and the federal laws of Canada applicable therein, without regard to
          conflict of law principles. Any disputes arising under or in connection with these terms
          shall be subject to the exclusive jurisdiction of the courts of the Province of Ontario.
        </p>
        <p className="legal-p">
          Questions?{' '}
          <a href="mailto:armaanrehmanshah1@gmail.com" className="legal-a">
            armaanrehmanshah1@gmail.com
          </a>
        </p>
      </section>

      <footer className="legal-page-footer">
        <span>© 2026 UofT Agent</span>
        <div className="legal-footer-links">
          <Link to="/privacy" className="legal-footer-link">Privacy Policy</Link>
          <Link to="/disclaimers" className="legal-footer-link">Disclaimers</Link>
          <a href="mailto:armaanrehmanshah1@gmail.com" className="legal-footer-link">Contact</a>
        </div>
      </footer>
    </div>
  )
}
