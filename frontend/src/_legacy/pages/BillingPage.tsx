import { useState } from "react"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, MoreHorizontal } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  useBusinessPartners,
  useCreateBusinessPartner,
  useUpdateBusinessPartner,
  useDeleteBusinessPartner,
  useProductServices,
  useCreateProductService,
  useUpdateProductService,
  useDeleteProductService,
  useContracts,
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
} from "@/features/billing"
import type {
  BusinessPartner,
  ProductService,
  Contract,
} from "@/features/billing"
import { useToast } from "@/components/ui/use-toast"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"

// Business Partners columns
const businessPartnerColumns: ColumnDef<BusinessPartner>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "category_name",
    header: "Category",
  },
  {
    accessorKey: "tax_id",
    header: "Tax ID",
  },
  {
    accessorKey: "email",
    header: "Email",
  },
  {
    id: "types",
    header: "Types",
    cell: ({ row }) => {
      const partner = row.original
      return (
        <div className="flex gap-1">
          {partner.is_customer && <Badge variant="secondary">Customer</Badge>}
          {partner.is_vendor && <Badge variant="secondary">Vendor</Badge>}
          {partner.is_supplier && <Badge variant="secondary">Supplier</Badge>}
        </div>
      )
    },
  },
]

// Product/Service columns
const productServiceColumns: ColumnDef<ProductService>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "category_name",
    header: "Category",
  },
  {
    accessorKey: "unit_price",
    header: "Unit Price",
    cell: ({ row }) => {
      const price = row.original.unit_price
      return price ? `$${price.toFixed(2)}` : "-"
    },
  },
  {
    id: "types",
    header: "Types",
    cell: ({ row }) => {
      const item = row.original
      return (
        <div className="flex gap-1">
          {item.is_product && <Badge variant="secondary">Product</Badge>}
          {item.is_service && <Badge variant="secondary">Service</Badge>}
        </div>
      )
    },
  },
]

// Contract columns
const contractColumns: ColumnDef<Contract>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "business_partner_name",
    header: "Business Partner",
  },
  {
    accessorKey: "start_date",
    header: "Start Date",
  },
  {
    accessorKey: "end_date",
    header: "End Date",
  },
  {
    accessorKey: "value",
    header: "Value",
    cell: ({ row }) => {
      const value = row.original.value
      return value ? `$${value.toFixed(2)}` : "-"
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant =
        status === "active" ? "success" : status === "expired" ? "destructive" : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

export function BillingPage() {
  const [activeTab, setActiveTab] = useState("partners")
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<{ type: string; id: number } | null>(null)

  // Business Partners
  const { data: partners, isLoading: partnersLoading } = useBusinessPartners()
  const createPartner = useCreateBusinessPartner()
  const updatePartner = useUpdateBusinessPartner()
  const deletePartner = useDeleteBusinessPartner()

  // Products/Services
  const { data: products, isLoading: productsLoading } = useProductServices()
  const createProduct = useCreateProductService()
  const updateProduct = useUpdateProductService()
  const deleteProduct = useDeleteProductService()

  // Contracts
  const { data: contracts, isLoading: contractsLoading } = useContracts()
  const createContract = useCreateContract()
  const updateContract = useUpdateContract()
  const deleteContract = useDeleteContract()

  const { toast } = useToast()

  const handleDelete = () => {
    if (!itemToDelete) return

    const mutations = {
      partner: deletePartner,
      product: deleteProduct,
      contract: deleteContract,
    }

    const mutation = mutations[itemToDelete.type as keyof typeof mutations]
    if (mutation) {
      mutation.mutate(itemToDelete.id, {
        onSuccess: () => {
          setDeleteDialogOpen(false)
          setItemToDelete(null)
        },
      })
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="Manage business partners, products/services, and contracts"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Billing" },
        ]}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="partners">Business Partners</TabsTrigger>
          <TabsTrigger value="products">Products/Services</TabsTrigger>
          <TabsTrigger value="contracts">Contracts</TabsTrigger>
        </TabsList>

        <TabsContent value="partners" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Business Partner
            </Button>
          </div>
          <DataTable
            data={partners?.results || []}
            columns={businessPartnerColumns}
            isLoading={partnersLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "partner", id: row.id })
                      setDeleteDialogOpen(true)
                    }}
                    className="text-destructive"
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>

        <TabsContent value="products" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Product/Service
            </Button>
          </div>
          <DataTable
            data={products?.results || []}
            columns={productServiceColumns}
            isLoading={productsLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "product", id: row.id })
                      setDeleteDialogOpen(true)
                    }}
                    className="text-destructive"
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>

        <TabsContent value="contracts" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Contract
            </Button>
          </div>
          <DataTable
            data={contracts?.results || []}
            columns={contractColumns}
            isLoading={contractsLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "contract", id: row.id })
                      setDeleteDialogOpen(true)
                    }}
                    className="text-destructive"
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>
      </Tabs>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete this item.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

