import type { QueryClient } from '@tanstack/react-query'

/** After any record change, refetch everything derived from the workbook:
 * KPIs, charts and alerts (portal config), lists, record details, activity,
 * form options (next IDs, lookup values) and chat suggestions. */
export function invalidateWorkbookData(queryClient: QueryClient, workbookId: string) {
  for (const key of ['portal', 'records', 'record-detail', 'record-activity', 'entity-schema', 'chat-suggestions']) {
    queryClient.invalidateQueries({ queryKey: [key, workbookId] })
  }
}
