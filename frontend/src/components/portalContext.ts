import { createContext, useContext } from 'react'
import type { RelatedFilter } from '../lib/portalView'

/** Portal-wide lookups and navigation, so deeply nested views (record
 * modal, chat) don't need these threaded through every component. */
export interface PortalNav {
  /** Display label for a raw worksheet name, e.g. "purchase_requests" -> "Purchase Requests". */
  labelFor: (worksheet: string) => string
  /** The entity's title column, used to show a readable record name. */
  titleColumnFor: (worksheet: string) => string | null
  /** Plain navigation to an entity page (no filter). */
  openEntity: (worksheet: string) => void
  /** Open an entity page filtered to records related to `parent`. */
  openRelated: (worksheet: string, parent: RelatedFilter) => void
}

export const PortalNavContext = createContext<PortalNav | null>(null)

export function usePortalNav(): PortalNav {
  const nav = useContext(PortalNavContext)
  if (!nav) throw new Error('usePortalNav must be used inside <PortalNavContext.Provider>')
  return nav
}
