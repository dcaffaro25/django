// Billing feature hooks
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type {
  BusinessPartner,
  BusinessPartnerCategory,
  ProductService,
  ProductServiceCategory,
  Contract,
  PaginatedResponse,
} from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as billingApi from "../api"

// Business Partner Categories
export function useBusinessPartnerCategories(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["business-partner-categories", tenant?.subdomain, params],
    queryFn: () => billingApi.getBusinessPartnerCategories(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateBusinessPartnerCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<BusinessPartnerCategory>) =>
      billingApi.createBusinessPartnerCategory(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partner-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create category",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateBusinessPartnerCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BusinessPartnerCategory> }) =>
      billingApi.updateBusinessPartnerCategory(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partner-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update category",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteBusinessPartnerCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => billingApi.deleteBusinessPartnerCategory(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partner-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete category",
        variant: "destructive",
      })
    },
  })
}

// Business Partners
export function useBusinessPartners(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["business-partners", tenant?.subdomain, params],
    queryFn: () => billingApi.getBusinessPartners(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateBusinessPartner() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<BusinessPartner>) =>
      billingApi.createBusinessPartner(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partners", tenant?.subdomain] })
      toast({ title: "Success", description: "Business partner created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create business partner",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateBusinessPartner() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BusinessPartner> }) =>
      billingApi.updateBusinessPartner(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partners", tenant?.subdomain] })
      toast({ title: "Success", description: "Business partner updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update business partner",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteBusinessPartner() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => billingApi.deleteBusinessPartner(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-partners", tenant?.subdomain] })
      toast({ title: "Success", description: "Business partner deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete business partner",
        variant: "destructive",
      })
    },
  })
}

// Product/Service Categories
export function useProductServiceCategories(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["product-service-categories", tenant?.subdomain, params],
    queryFn: () => billingApi.getProductServiceCategories(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateProductServiceCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<ProductServiceCategory>) =>
      billingApi.createProductServiceCategory(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-service-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create category",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateProductServiceCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ProductServiceCategory> }) =>
      billingApi.updateProductServiceCategory(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-service-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update category",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteProductServiceCategory() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => billingApi.deleteProductServiceCategory(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-service-categories", tenant?.subdomain] })
      toast({ title: "Success", description: "Category deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete category",
        variant: "destructive",
      })
    },
  })
}

// Products/Services
export function useProductServices(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["product-services", tenant?.subdomain, params],
    queryFn: () => billingApi.getProductServices(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateProductService() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<ProductService>) =>
      billingApi.createProductService(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-services", tenant?.subdomain] })
      toast({ title: "Success", description: "Product/Service created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create product/service",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateProductService() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ProductService> }) =>
      billingApi.updateProductService(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-services", tenant?.subdomain] })
      toast({ title: "Success", description: "Product/Service updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update product/service",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteProductService() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => billingApi.deleteProductService(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-services", tenant?.subdomain] })
      toast({ title: "Success", description: "Product/Service deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete product/service",
        variant: "destructive",
      })
    },
  })
}

// Contracts
export function useContracts(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["contracts", tenant?.subdomain, params],
    queryFn: () => billingApi.getContracts(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateContract() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<Contract>) =>
      billingApi.createContract(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contracts", tenant?.subdomain] })
      toast({ title: "Success", description: "Contract created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create contract",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateContract() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Contract> }) =>
      billingApi.updateContract(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contracts", tenant?.subdomain] })
      toast({ title: "Success", description: "Contract updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update contract",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteContract() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => billingApi.deleteContract(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contracts", tenant?.subdomain] })
      toast({ title: "Success", description: "Contract deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete contract",
        variant: "destructive",
      })
    },
  })
}

