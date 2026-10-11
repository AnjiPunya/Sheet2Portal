// Display-only formatting for raw worksheet/field names: "Project_Manager"
// -> "Project Manager". Data, filters and API calls always keep the original
// name. Mirrors humanize() in backend/app/services/analysis/text.py so labels
// read the same whether they were formatted server- or client-side.

// Kept upper-case even inside an all-caps name like "PR_ID" or "ITEM_SKU".
const ACRONYMS = new Set([
  'ID', 'PR', 'PO', 'SKU', 'HR', 'GST', 'VAT', 'UOM', 'KPI', 'ETA', 'URL', 'API', 'USD', 'INR', 'EUR', 'GBP', 'QTY',
])

function displayWord(word: string, allCapsName: boolean): string {
  if (ACRONYMS.has(word.toUpperCase())) return word.toUpperCase()
  if (allCapsName) return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  if (word === word.toUpperCase()) return word // an acronym in a mixed-case name
  return word.charAt(0).toUpperCase() + word.slice(1)
}

export function formatLabel(name: string): string {
  const spaced = name.replace(/[_-]+/g, ' ').replace(/(?<=[a-z0-9])(?=[A-Z])/g, ' ')
  const allCapsName = name === name.toUpperCase()
  return spaced
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => displayWord(word, allCapsName))
    .join(' ')
}
