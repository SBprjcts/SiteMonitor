import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProductUrlWatchForm } from "@/components/watches/ProductUrlWatchForm"

export function NewWatchPage() {
  return (
    <>
      <PageHeader title="New watch" description="Watch a product, a style code, or a keyword set." />
      <Tabs defaultValue="product" className="gap-6">
        <TabsList>
          <TabsTrigger value="product">Product link</TabsTrigger>
          <TabsTrigger value="style_code">Style code</TabsTrigger>
          <TabsTrigger value="keyword">Keywords</TabsTrigger>
        </TabsList>
        <TabsContent value="product">
          <ProductUrlWatchForm />
        </TabsContent>
        <TabsContent value="style_code">
          <ComingSoon what="Watching a style code (like DD1391-100) across every store" />
        </TabsContent>
        <TabsContent value="keyword">
          <ComingSoon what="Keyword watching (like nike, low, panda, -gs)" />
        </TabsContent>
      </Tabs>
    </>
  )
}
