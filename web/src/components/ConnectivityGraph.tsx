import { useMemo } from 'react'

const DEFAULT_NODES = [
  'RFIs',
  'Meetings',
  'Change Events',
  'Submittals',
  'Specs',
  'Daily Reports',
  'Buyout',
  'Schedule',
  'Punchlist',
  'As-Builts',
]

type ActiveLink = {
  from: string
  to: string
}

type Props = {
  activeLinks?: ActiveLink[]
  pulseNodes?: string[]
  completedPasses?: number
  totalPasses?: number
}

function nodePosition(index: number, total: number, radius: number) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2
  return {
    x: 200 + radius * Math.cos(angle),
    y: 200 + radius * Math.sin(angle),
  }
}

export function ConnectivityGraph({
  activeLinks = [],
  pulseNodes = [],
  completedPasses = 0,
  totalPasses = 20,
}: Props) {
  const nodes = DEFAULT_NODES
  const positions = useMemo(
    () => nodes.map((_, index) => nodePosition(index, nodes.length, 145)),
    [nodes],
  )

  const recent = activeLinks.slice(-8)
  const lit = new Set(pulseNodes)

  return (
    <div className="connectivity">
      <div className="connectivity-meta">
        <span>Project graph</span>
        <span>
          {completedPasses}/{totalPasses} passes linked
        </span>
      </div>
      <svg viewBox="0 0 400 400" className="connectivity-svg" role="img" aria-label="Connectivity graph">
        <circle cx="200" cy="200" r="168" className="connectivity-ring" />
        {recent.map((link, index) => {
          const fromIndex = nodes.indexOf(link.from)
          const toIndex = nodes.indexOf(link.to)
          if (fromIndex < 0 || toIndex < 0) return null
          const a = positions[fromIndex]
          const b = positions[toIndex]
          return (
            <line
              key={`${link.from}-${link.to}-${index}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className="connectivity-edge active"
            />
          )
        })}
        {nodes.map((node, index) => {
          const pos = positions[index]
          const isLit = lit.has(node) || recent.some((l) => l.from === node || l.to === node)
          return (
            <g key={node} className={isLit ? 'connectivity-node lit' : 'connectivity-node'}>
              <circle cx={pos.x} cy={pos.y} r={isLit ? 18 : 14} />
              <text x={pos.x} y={pos.y + 34} textAnchor="middle">
                {node}
              </text>
            </g>
          )
        })}
        <g className="connectivity-core">
          <circle cx="200" cy="200" r="36" />
          <text x="200" y="196" textAnchor="middle">
            Lessons
          </text>
          <text x="200" y="214" textAnchor="middle">
            Graph
          </text>
        </g>
      </svg>
    </div>
  )
}
