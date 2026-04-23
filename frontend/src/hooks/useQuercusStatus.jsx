import { useQuery } from '@tanstack/react-query'

import client from '../api/client'

const QUERCUS_STATUS_STALE_TIME_MS = 10 * 60 * 1000
const QUERCUS_STATUS_GC_TIME_MS = 30 * 60 * 1000

export function useQuercusStatus() {
  return useQuery({
    queryKey: ['quercus-token-status'],
    retry: false,
    staleTime: QUERCUS_STATUS_STALE_TIME_MS,
    gcTime: QUERCUS_STATUS_GC_TIME_MS,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      try {
        const response = await client.get('/api/courses/quercus-token')
        return {
          hasToken: Boolean(response.data?.token),
        }
      } catch (error) {
        if (error?.response?.status === 404) {
          return { hasToken: false }
        }
        throw error
      }
    },
  })
}
