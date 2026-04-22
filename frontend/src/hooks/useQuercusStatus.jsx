import { useQuery } from '@tanstack/react-query'

import client from '../api/client'

export function useQuercusStatus() {
  return useQuery({
    queryKey: ['quercus-token-status'],
    retry: false,
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
