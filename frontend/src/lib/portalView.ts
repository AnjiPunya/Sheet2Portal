// Which page of the portal is showing, plus the optional related-record
// filter set by a record's "View all" link (e.g. Tasks for one Project).
// Kept free of React/browser imports so it can be unit-tested with node:test.

export interface RelatedFilter {
  /** Raw worksheet name of the parent record, e.g. "Projects". */
  worksheet: string
  /** The parent record's id -- what the backend filters by. */
  recordId: string
  /** Readable name of the parent, for the active-filter chip. */
  label: string
}

export interface EntityViewState {
  worksheet: string
  related?: RelatedFilter
}

export type PortalView = 'dashboard' | 'diagnostics' | EntityViewState

/** Plain navigation to an entity (tabs, alerts, chat references): no filter. */
export function entityView(worksheet: string): EntityViewState {
  return { worksheet }
}

/** "View all" from a parent record: the entity, filtered to that parent. */
export function relatedEntityView(worksheet: string, parent: RelatedFilter): EntityViewState {
  return { worksheet, related: { ...parent } }
}

export function clearRelatedFilter(view: EntityViewState): EntityViewState {
  return { worksheet: view.worksheet }
}

/** Identifies the active nav tab -- a filtered entity is still its tab. */
export function navKey(view: PortalView): string {
  return typeof view === 'string' ? view : `entity:${view.worksheet}`
}

/** Identifies the entity page instance; changes whenever the filter does so
 * paging/search state resets instead of carrying over between parents. */
export function entityPageKey(view: EntityViewState): string {
  return view.related ? `${view.worksheet}|${view.related.worksheet}:${view.related.recordId}` : view.worksheet
}
