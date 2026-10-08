import { useState, type FormEvent } from "react"
import { Navigate, useLocation, useNavigate } from "react-router"
import { BellRing } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useLogin, useMe, useRegister } from "@/hooks/useAuth"

const MIN_PASSWORD_LENGTH = 8 // matches RegisterRequest in backend/app/schemas/auth.py

export function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const { data: user } = useMe()
  const login = useLogin()
  const register = useRegister()
  const navigate = useNavigate()
  const location = useLocation()

  const registering = mode === "register"
  const submit = registering ? register : login
  const destination = (location.state as { from?: string } | null)?.from ?? "/"

  if (user) return <Navigate to={destination} replace />

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    submit.mutate(
      { email, password },
      { onSuccess: () => navigate(destination, { replace: true }) },
    )
  }

  function switchMode() {
    login.reset()
    register.reset()
    setMode(registering ? "login" : "register")
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 text-foreground">
      <Card className="w-full max-w-sm gap-6 p-6">
        <div className="flex items-center gap-2 font-heading text-lg font-semibold">
          <BellRing className="size-5 text-primary" />
          SiteMonitor
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              required
              minLength={registering ? MIN_PASSWORD_LENGTH : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {registering && (
              <p className="text-xs text-muted-foreground">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
          </div>

          {submit.error && (
            <p role="alert" className="text-sm text-destructive">
              {submit.error.message}
            </p>
          )}

          <Button type="submit" disabled={submit.isPending}>
            {registering ? "Create account" : "Log in"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          {registering ? "Already have an account?" : "New here?"}{" "}
          <button type="button" className="text-foreground underline" onClick={switchMode}>
            {registering ? "Log in" : "Create an account"}
          </button>
        </p>
      </Card>
    </div>
  )
}
