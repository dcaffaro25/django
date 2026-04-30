import { Navigate, useSearchParams } from "react-router-dom"

/**
 * Redirects the deprecated /recon/suggestions URL to the merged Execuções
 * page. ?task_id=X becomes ?id=X so deep links from saved emails / bookmarks
 * keep working after the merge.
 */
export function SuggestionsLegacyRedirect() {
  const [params] = useSearchParams()
  const taskId = params.get("task_id")
  const target = taskId ? `/recon/tasks?id=${encodeURIComponent(taskId)}` : "/recon/tasks"
  return <Navigate to={target} replace />
}
