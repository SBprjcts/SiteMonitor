import { useState, type FormEvent } from "react"
import { Loader2, Plus } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAddStore } from "@/hooks/useStores"
import { normalizeDomain } from "@/lib/format"

export function AddStoreDialog() {
  const [open, setOpen] = useState(false)
  const [domainInput, setDomainInput] = useState("")
  const [name, setName] = useState("")
  const [touched, setTouched] = useState(false)
  const addStore = useAddStore()

  const domain = normalizeDomain(domainInput)
  const domainError = touched && !domain ? "Enter a store URL or domain, like nrml.ca" : null

  function reset() {
    setDomainInput("")
    setName("")
    setTouched(false)
    addStore.reset()
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!domain) return
    addStore.mutate(
      { domain, name: name.trim() || undefined },
      {
        onSuccess: (store) => {
          toast.success(`Now monitoring ${store.name}`)
          setOpen(false)
          reset()
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Add store
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add a Shopify store</DialogTitle>
            <DialogDescription>
              We check that the store exposes Shopify&apos;s product feed before adding it.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <Label htmlFor="store-domain">Store URL or domain</Label>
            <Input
              id="store-domain"
              placeholder="nrml.ca"
              value={domainInput}
              onChange={(e) => setDomainInput(e.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={!!domainError}
              autoFocus
            />
            {domainError && <p className="text-sm text-destructive">{domainError}</p>}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="store-name">
              Display name <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="store-name"
              placeholder="NRML"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {addStore.error && <p className="text-sm text-destructive">{addStore.error.message}</p>}

          <DialogFooter>
            <Button type="submit" disabled={addStore.isPending}>
              {addStore.isPending && <Loader2 className="animate-spin" />}
              {addStore.isPending ? "Checking store…" : "Add store"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
