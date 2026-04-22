const googleAuthUrl = `${import.meta.env.VITE_API_URL || ''}/auth/google`

export default function Login() {
  return (
    <main className="login-screen">
      <div className="login-card">
        <div className="icon-wrap">
          <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
            <path
              d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z"
              fill="oklch(68% 0.16 240)"
              opacity="0.55"
            />
            <circle cx="22.5" cy="8" r="1.1" fill="oklch(80% 0.12 200)" opacity="0.8" />
            <circle cx="20.5" cy="5.2" r="0.7" fill="oklch(75% 0.14 220)" opacity="0.6" />
            <circle cx="24.2" cy="6" r="0.6" fill="oklch(72% 0.14 260)" opacity="0.5" />
          </svg>
        </div>

        <h1>UofT Agent</h1>
        <p className="tagline">Your AI academic assistant</p>
        <div className="divider" />
        <button className="btn-google" type="button" onClick={() => window.location.assign(googleAuthUrl)}>
          <svg className="g-logo" viewBox="0 0 18 18" aria-hidden="true">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4" />
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
            <path d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" fill="#FBBC05" />
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
          </svg>
          Sign in with Google
        </button>
        <p className="footnote">For University of Toronto students</p>
      </div>
    </main>
  )
}
