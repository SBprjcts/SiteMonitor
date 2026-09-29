import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { addStore, listStores, updateStore } from "@/api/client"
import type { Store } from "@/api/types"

const STORES_KEY = ["stores"] as const

export function useStores() {
  return useQuery({ queryKey: STORES_KEY, queryFn: listStores })
}

export function useToggleStore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateStore(id, { enabled }),
    // Flip the switch immediately and roll back if the request fails.
    onMutate: async ({ id, enabled }) => {
      await queryClient.cancelQueries({ queryKey: STORES_KEY })
      const previous = queryClient.getQueryData<Store[]>(STORES_KEY)
      queryClient.setQueryData<Store[]>(STORES_KEY, (stores) =>
        stores?.map((s) => (s.id === id ? { ...s, enabled } : s)),
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      queryClient.setQueryData(STORES_KEY, context?.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: STORES_KEY }),
  })
}

export function useAddStore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: addStore,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: STORES_KEY }),
  })
}
