import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"

import { getMe, login, logout, register } from "@/api/client"
import type { User } from "@/api/types"

export const ME_KEY = ["me"] as const

/** The logged-in user: undefined while loading, null when nobody is logged in. */
export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: getMe, staleTime: 60_000, retry: false })
}

/**
 * Switches who is logged in (null logs out) and drops everything the previous user loaded.
 *
 * The order matters: `queryClient.clear()` would also remove the "me" query that
 * RequireAuth is subscribed to, so the page would never be told the user changed.
 */
function setCurrentUser(queryClient: QueryClient, user: User | null) {
  queryClient.setQueryData(ME_KEY, user)
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
}

function useSignIn(mutationFn: typeof login) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (user) => setCurrentUser(queryClient, user),
  })
}

export function useLogin() {
  return useSignIn(login)
}

export function useRegister() {
  return useSignIn(register)
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSuccess: () => setCurrentUser(queryClient, null),
  })
}
