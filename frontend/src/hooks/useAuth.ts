import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { getMe, login, logout, register } from "@/api/client"
import type { User } from "@/api/types"

export const ME_KEY = ["me"] as const

/** The logged-in user: undefined while loading, null when nobody is logged in. */
export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: getMe, staleTime: 60_000, retry: false })
}

function useSignIn(mutationFn: typeof login) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (user: User) => {
      // A different person may have been logged in before: drop everything they loaded.
      queryClient.clear()
      queryClient.setQueryData(ME_KEY, user)
    },
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
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(ME_KEY, null)
    },
  })
}
