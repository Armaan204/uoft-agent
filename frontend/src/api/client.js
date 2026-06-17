import axios from 'axios'

export const TOKEN_KEY = 'uoft-agent-token'
const baseURL = import.meta.env.VITE_API_URL || ''

const client = axios.create({
  baseURL,
})

client.interceptors.request.use((config) => {
  const token = window.localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      window.localStorage.removeItem(TOKEN_KEY)
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }

    const httpStatus = error?.response?.status
    const detail = error?.response?.data?.detail
    const isQuercusExpired = httpStatus === 424 && detail === 'quercus_token_invalid'
    const isQuercusMissing = httpStatus === 400 && detail === 'No Quercus token provided and no saved token found.'
    if ((isQuercusExpired || isQuercusMissing) && window.location.pathname !== '/onboarding') {
      window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
      window.location.assign('/onboarding?expired=true')
    }

    return Promise.reject(error)
  },
)

export default client
