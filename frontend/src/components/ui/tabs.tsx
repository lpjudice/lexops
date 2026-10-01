import { useState } from 'react'

export function Tabs({ defaultValue, children, className = '' }) {
  const [activeValue, setActiveValue] = useState(defaultValue)

  return (
    <div className={className}>
      {Array.isArray(children)
        ? children.map((child) => {
          if (child?.type?.name === 'TabsList') {
            return (
              <div key="list">
                {child.props.children.map((trigger) => (
                  <button
                    key={trigger.props.value}
                    onClick={() => setActiveValue(trigger.props.value)}
                    className={`px-4 py-2 font-medium border-b-2 transition ${
                      activeValue === trigger.props.value
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    {trigger.props.children}
                  </button>
                ))}
              </div>
            )
          }
          return null
        })
        : null}

      {Array.isArray(children)
        ? children.map((child) => {
          if (child?.type?.name === 'TabsContent' && child.props.value === activeValue) {
            return <div key={child.props.value}>{child.props.children}</div>
          }
          return null
        })
        : null}
    </div>
  )
}

export function TabsList({ children, className = '' }) {
  return <div className={`flex gap-0 border-b border-gray-200 ${className}`}>{children}</div>
}

export function TabsTrigger({ value, children, className = '' }) {
  return (
    <button className={`px-4 py-2 font-medium ${className}`} data-value={value}>
      {children}
    </button>
  )
}

export function TabsContent({ value, children, className = '' }) {
  return <div className={`pt-6 ${className}`}>{children}</div>
}
