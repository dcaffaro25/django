// Billing API endpoints
import { apiClient } from "@/lib/api-client"
import type {
  BusinessPartner,
  BusinessPartnerCategory,
  ProductService,
  ProductServiceCategory,
  Contract,
  PaginatedResponse,
} from "@/types"

// Business Partner Categories
export async function getBusinessPartnerCategories(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<BusinessPartnerCategory>> {
  return apiClient.get<PaginatedResponse<BusinessPartnerCategory>>(
    "/api/business_partner_categories/",
    params
  )
}

export async function createBusinessPartnerCategory(
  tenant: string,
  data: Partial<BusinessPartnerCategory>
): Promise<BusinessPartnerCategory> {
  return apiClient.post<BusinessPartnerCategory>("/api/business_partner_categories/", data)
}

export async function updateBusinessPartnerCategory(
  tenant: string,
  id: number,
  data: Partial<BusinessPartnerCategory>
): Promise<BusinessPartnerCategory> {
  return apiClient.put<BusinessPartnerCategory>(
    `/api/business_partner_categories/${id}/`,
    data
  )
}

export async function deleteBusinessPartnerCategory(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/business_partner_categories/${id}/`)
}

// Business Partners
export async function getBusinessPartners(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<BusinessPartner>> {
  return apiClient.get<PaginatedResponse<BusinessPartner>>("/api/business_partners/", params)
}

export async function createBusinessPartner(
  tenant: string,
  data: Partial<BusinessPartner>
): Promise<BusinessPartner> {
  return apiClient.post<BusinessPartner>("/api/business_partners/", data)
}

export async function updateBusinessPartner(
  tenant: string,
  id: number,
  data: Partial<BusinessPartner>
): Promise<BusinessPartner> {
  return apiClient.put<BusinessPartner>(`/api/business_partners/${id}/`, data)
}

export async function deleteBusinessPartner(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/business_partners/${id}/`)
}

// Product/Service Categories
export async function getProductServiceCategories(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ProductServiceCategory>> {
  return apiClient.get<PaginatedResponse<ProductServiceCategory>>(
    "/api/product_service_categories/",
    params
  )
}

export async function createProductServiceCategory(
  tenant: string,
  data: Partial<ProductServiceCategory>
): Promise<ProductServiceCategory> {
  return apiClient.post<ProductServiceCategory>("/api/product_service_categories/", data)
}

export async function updateProductServiceCategory(
  tenant: string,
  id: number,
  data: Partial<ProductServiceCategory>
): Promise<ProductServiceCategory> {
  return apiClient.put<ProductServiceCategory>(`/api/product_service_categories/${id}/`, data)
}

export async function deleteProductServiceCategory(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/product_service_categories/${id}/`)
}

// Products/Services
export async function getProductServices(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ProductService>> {
  return apiClient.get<PaginatedResponse<ProductService>>("/api/product_services/", params)
}

export async function createProductService(
  tenant: string,
  data: Partial<ProductService>
): Promise<ProductService> {
  return apiClient.post<ProductService>("/api/product_services/", data)
}

export async function updateProductService(
  tenant: string,
  id: number,
  data: Partial<ProductService>
): Promise<ProductService> {
  return apiClient.put<ProductService>(`/api/product_services/${id}/`, data)
}

export async function deleteProductService(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/product_services/${id}/`)
}

// Contracts
export async function getContracts(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Contract>> {
  return apiClient.get<PaginatedResponse<Contract>>("/api/contracts/", params)
}

export async function createContract(tenant: string, data: Partial<Contract>): Promise<Contract> {
  return apiClient.post<Contract>("/api/contracts/", data)
}

export async function updateContract(
  tenant: string,
  id: number,
  data: Partial<Contract>
): Promise<Contract> {
  return apiClient.put<Contract>(`/api/contracts/${id}/`, data)
}

export async function deleteContract(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/contracts/${id}/`)
}

