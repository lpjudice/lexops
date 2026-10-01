import { useState } from 'react'

export function Dialog({ open, onOpenChange, children }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => onOpenChange(false)}>
      {children}
    </div>
  )
}

export function DialogContent({ className = '', children }) {
  return (
    <div
      className={`bg-white rounded-lg shadow-lg max-w-2xl w-full mx-4 ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  )
}

export function DialogHeader({ children }) {
  return <div className="border-b px-6 py-4">{children}</div>
}

export function DialogTitle({ children }) {
  return <h2 className="text-lg font-semibold">{children}</h2>
}
