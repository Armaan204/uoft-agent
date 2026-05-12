import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient } from '@tanstack/react-query'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'

import App from './App'
import { AuthProvider } from './hooks/useAuth'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 24 * 60 * 60 * 1000, // 24 hours — keep entries in the persisted cache across restarts
    },
  },
})

const persister = createSyncStoragePersister({ storage: window.localStorage })

ReactDOM.createRoot(document.getElementById('app')).render(
  <React.StrictMode>
    <BrowserRouter>
      <PersistQueryClientProvider client={queryClient} persistOptions={{ persister, maxAge: 24 * 60 * 60 * 1000 }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </PersistQueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
