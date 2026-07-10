import axios from 'axios'

const client = axios.create({
  withCredentials: true,
})

let refreshPromise = null

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const requestUrl = error?.config?.url || ''
    const httpStatus = error?.response?.status

    const isAuthEndpoint = requestUrl.startsWith('/auth/') && requestUrl !== '/auth/me'
    if (httpStatus === 401 && !isAuthEndpoint && !error.config._retry) {
      error.config._retry = true
      if (!refreshPromise) {
        refreshPromise = client.post('/auth/refresh').finally(() => {
          refreshPromise = null
        })
      }
      try {
        await refreshPromise
        return client(error.config)
      } catch {
        window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        if (window.location.pathname !== '/login' && window.location.pathname !== '/signin') {
          window.location.assign('/login')
        }
        return Promise.reject(error)
      }
    }

    const detail = error?.response?.data?.detail
    const isQuercusExpired = httpStatus === 424 && detail === 'quercus_token_invalid'
    if (isQuercusExpired && window.location.pathname !== '/onboarding') {
      window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
      window.location.assign('/onboarding?expired=true')
    }

    return Promise.reject(error)
  },
)

export default client
