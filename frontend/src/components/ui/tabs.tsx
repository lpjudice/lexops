import { createContext, useState, useContext } from 'react'

const TabsContext = createContext({ activeValue: '', setActiveValue: (v: string) => {} })

export function Tabs({ defaultValue, children, className = '' }) {
  const [activeValue, setActiveValue] = useState(defaultValue)

  return (
    <TabsContext.Provider value={{ activeValue, setActiveValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className = '' }) {
  return (
    <div className={`flex gap-0 border-b border-gray-200 ${className}`}>
      {children}
    </div>
  )
}

export function TabsTrigger({ value, children, className = '' }) {
  const { activeValue, setActiveValue } = useContext(TabsContext)

  return (
    <button
      onClick={() => setActiveValue(value)}
      className={`px-4 py-2 font-medium border-b-2 transition ${
        activeValue === value
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-600 hover:text-gray-900'
      } ${className}`}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, children, className = '' }) {
  const { activeValue } = useContext(TabsContext)

  if (activeValue !== value) return null

  return <div className={`pt-6 ${className}`}>{children}</div>
}
