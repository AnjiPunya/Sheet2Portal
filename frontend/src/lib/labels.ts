// Display-only formatting for raw worksheet/field names: "Project_Manager"
// -> "Project Manager", "Stock_Kg" -> "Stock (kg)". Data, filters and API
// calls always keep the original name. Mirrors humanize() in
// backend/app/services/analysis/text.py (both are tested against the same
// table) so labels read the same whether formatted server- or client-side.

// Kept upper-case even inside an all-caps name like "PR_ID" or "ITEM_SKU".
const ACRONYMS = new Set([
  'ID', 'PR', 'PO', 'SKU', 'HR', 'GST', 'VAT', 'UOM', 'KPI', 'ETA', 'URL', 'API', 'USD', 'INR', 'EUR', 'GBP', 'QTY', 'PL', 'NTU',
])
// Lower-case connecting words (never the first word).
const SMALL_WORDS = new Set(['or', 'of', 'per', 'and', 'to', 'in', 'by', 'for', 'the', 'a', 'an', 'on', 'at', 'vs', 'out'])
// Units, written the conventional way.
const UNITS: Record<string, string> = {
  kg: 'kg', g: 'g', mg: 'mg', l: 'L', ml: 'mL', ppt: 'ppt', ppm: 'ppm', ntu: 'NTU',
  acres: 'acres', acre: 'acres', ha: 'ha', hectares: 'hectares', km: 'km', cm: 'cm', mm: 'mm',
  inr: 'INR', usd: 'USD', eur: 'EUR', gbp: 'GBP', percent: '%', pct: '%', '%': '%',
}
const TEMPERATURE = new Set(['temperature', 'temp'])

function isUnit(words: string[], index: number, connectingPer: boolean): boolean {
  const word = words[index].toLowerCase()
  if (connectingPer) return true
  // Temperature_C -> Temperature (°C); a lone "C" elsewhere isn't a unit.
  if (word === 'c') return index > 0 && TEMPERATURE.has(words[index - 1].toLowerCase())
  return word in UNITS
}

function unitGroup(units: string[], previous: string): string {
  const lowered = units.map((u) => u.toLowerCase())
  if (lowered.join(' ') === 'mg l') return 'mg/L'
  if (lowered.join(' ') === 'c' && TEMPERATURE.has(previous.toLowerCase())) return '°C'
  return lowered.map((u) => (u === 'per' ? 'per' : (UNITS[u] ?? u))).join(' ')
}

function displayWord(word: string, allCapsName: boolean, index: number): string {
  if (ACRONYMS.has(word.toUpperCase())) return word.toUpperCase()
  if (index > 0 && SMALL_WORDS.has(word.toLowerCase())) return word.toLowerCase()
  if (allCapsName) return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  if (word === word.toUpperCase()) return word // an acronym in a mixed-case name
  // Mixed-case terms such as "pH" or "eBay" keep their spelling.
  if (word.charAt(0) === word.charAt(0).toLowerCase() && /[A-Z]/.test(word.slice(1))) return word
  return word.charAt(0).toUpperCase() + word.slice(1)
}

export function formatLabel(name: string): string {
  if (name.includes('(')) {
    // Already formatted ("Stock (kg)"): format only the part before the suffix.
    const at = name.indexOf('(')
    const head = name.slice(0, at)
    return head.trim() ? `${formatLabel(head)} ${name.slice(at)}`.trim() : name
  }
  const spaced = name.replace(/[_-]+/g, ' ').replace(/(?<=[a-z]{2})(?=[A-Z])|(?<=[0-9])(?=[A-Z])/g, ' ')
  const allCapsName = name === name.toUpperCase()
  const words = spaced.split(/\s+/).filter(Boolean)
  let start = words.length
  while (start > 1 && isUnit(words, start - 1, words[start - 1].toLowerCase() === 'per' && start < words.length)) start -= 1
  if (start === words.length - 1 && words[start]?.toLowerCase() === 'per') start += 1 // a dangling "per" isn't a unit group
  const head = words.slice(0, start).map((w, i) => displayWord(w, allCapsName, i))
  if (start < words.length) head.push(`(${unitGroup(words.slice(start), start ? words[start - 1] : '')})`)
  return head.join(' ')
}
