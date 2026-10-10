import { useRef, useState, type DragEvent } from 'react'

interface Props {
  onFileSelected: (file: File) => void
  disabled?: boolean
}

export function UploadDropzone({ onFileSelected, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) onFileSelected(file)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={disabled ? undefined : handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      aria-disabled={disabled}
      className={`flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-12 text-center transition-colors
        ${isDragging ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-slate-50'}
        ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-indigo-400'}`}
    >
      <p className="font-medium text-slate-700">Drag and drop your Excel or CSV file here</p>
      <p className="text-sm text-slate-400">or click to browse — .xlsx or .csv, up to 25MB</p>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.csv"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFileSelected(file)
          e.target.value = ''
        }}
      />
    </div>
  )
}
