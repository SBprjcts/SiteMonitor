import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  createWatch,
  deleteWatch,
  getProduct,
  listProductEvents,
  listWatches,
  lookupProduct,
  updateWatch,
} from "@/api/client"
import type { WatchListItem } from "@/api/types"

const WATCHES_KEY = ["watches"] as const

export function useWatches() {
  return useQuery({ queryKey: WATCHES_KEY, queryFn: listWatches })
}

export function useCreateWatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createWatch,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: WATCHES_KEY }),
  })
}

export function useToggleWatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => updateWatch(id, { active }),
    onMutate: async ({ id, active }) => {
      await queryClient.cancelQueries({ queryKey: WATCHES_KEY })
      const previous = queryClient.getQueryData<WatchListItem[]>(WATCHES_KEY)
      queryClient.setQueryData<WatchListItem[]>(WATCHES_KEY, (watches) =>
        watches?.map((w) => (w.id === id ? { ...w, active } : w)),
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      queryClient.setQueryData(WATCHES_KEY, context?.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: WATCHES_KEY }),
  })
}

export function useDeleteWatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteWatch,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: WATCHES_KEY }),
  })
}

export function useLookupProduct() {
  return useMutation({ mutationFn: lookupProduct })
}

export function useProduct(id: number) {
  return useQuery({ queryKey: ["products", id], queryFn: () => getProduct(id) })
}

export function useProductEvents(id: number) {
  return useQuery({ queryKey: ["products", id, "events"], queryFn: () => listProductEvents(id) })
}
