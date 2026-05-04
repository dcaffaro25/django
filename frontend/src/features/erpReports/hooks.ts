import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { erpReportsApi, type PedidoReport, type PedidoReportFilters } from "./api"


const KEY_PEDIDOS = ["erp", "reports", "pedidos"] as const


export function usePedidoReport(filters: PedidoReportFilters = {}) {
  return useQuery({
    queryKey: [...KEY_PEDIDOS, filters] as const,
    queryFn: () => erpReportsApi.pedidos(filters),
    staleTime: 30_000,
  })
}


/** Triggers a live pipeline run on the backend, then returns the
 *  fresh snapshot. The mutation invalidates the report cache so the
 *  next ``usePedidoReport`` reads land on whatever the new run
 *  produced. */
export function useRefreshPedidoReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filters: PedidoReportFilters = {}) =>
      erpReportsApi.refreshPedidos(filters),
    onSuccess: (data: PedidoReport) => {
      qc.invalidateQueries({ queryKey: KEY_PEDIDOS })
      // Hydrate the cache for the no-filter view immediately.
      qc.setQueryData([...KEY_PEDIDOS, {}], data)
    },
  })
}
