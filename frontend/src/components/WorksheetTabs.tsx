import type { WorksheetOut } from '../types/workbook'

interface Props {
  sheets: WorksheetOut[]
  activeIndex: number
  onSelect: (index: number) => void
}

export function WorksheetTabs({ sheets, activeIndex, onSelect }: Props) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {sheets.map((sheet, i) => (
        <button
          key={sheet.sheet_index}
          onClick={() => onSelect(i)}
          className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors
            ${i === activeIndex ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
        >
          {sheet.name}
          <span className="ml-1.5 text-xs text-slate-400">({sheet.row_count})</span>
        </button>
      ))}
    </div>
  )
}
