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

const CX = 200
const CY = 200
const CORE_R = 42
const NODE_R = 14
const NODE_R_LIT = 18
const RING_R = 145

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
    x: CX + radius * Math.cos(angle),
    y: CY + radius * Math.sin(angle),
  }
}

/** Segment from the core rim to the node rim — never crosses the center label. */
function spokeEndpoints(
  nx: number,
  ny: number,
  nodeRadius: number,
): { x1: number; y1: number; x2: number; y2: number } {
  const dx = nx - CX
  const dy = ny - CY
  const dist = Math.hypot(dx, dy) || 1
  const ux = dx / dist
  const uy = dy / dist
  return {
    x1: CX + CORE_R * ux,
    y1: CY + CORE_R * uy,
    x2: nx - nodeRadius * ux,
    y2: ny - nodeRadius * uy,
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
    () => nodes.map((_, index) => nodePosition(index, nodes.length, RING_R)),
    [nodes],
  )

  const recent = activeLinks.slice(-12)

  // Peripheral modules currently exchanging with the Lessons Learned core.
  const activeNodeNames = useMemo(() => {
    const lit = new Set<string>()
    for (const link of recent) {
      if (nodes.includes(link.from)) lit.add(link.from)
      if (nodes.includes(link.to)) lit.add(link.to)
    }
    for (const name of pulseNodes) {
      if (nodes.includes(name)) lit.add(name)
    }
    return nodes.filter((name) => lit.has(name))
  }, [recent, pulseNodes, nodes])

  const lit = new Set(activeNodeNames)

  return (
    <div className="connectivity">
      <div className="connectivity-meta">
        <span>Project graph</span>
        <span>
          {completedPasses}/{totalPasses} passes linked
        </span>
      </div>
      <svg viewBox="0 0 400 400" className="connectivity-svg" role="img" aria-label="Connectivity graph">
        <defs>
          <marker
            id="flow-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="4.5"
            markerHeight="4.5"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M 0 1.2 L 9 5 L 0 8.8 Z" className="connectivity-arrow" />
          </marker>
        </defs>

        <circle cx={CX} cy={CY} r="168" className="connectivity-ring" />

        {/* Idle spokes — faint hub-and-spoke structure */}
        {positions.map((pos, index) => {
          const spoke = spokeEndpoints(pos.x, pos.y, NODE_R)
          return (
            <line
              key={`idle-${nodes[index]}`}
              x1={spoke.x1}
              y1={spoke.y1}
              x2={spoke.x2}
              y2={spoke.y2}
              className="connectivity-edge idle"
            />
          )
        })}

        {/* Active bidirectional flows: core → module and module → core */}
        {activeNodeNames.map((name) => {
          const index = nodes.indexOf(name)
          const pos = positions[index]
          const spoke = spokeEndpoints(pos.x, pos.y, NODE_R_LIT)
          return (
            <g key={`flow-${name}`} className="connectivity-flow">
              <line
                x1={spoke.x1}
                y1={spoke.y1}
                x2={spoke.x2}
                y2={spoke.y2}
                className="connectivity-edge flow-out"
                markerEnd="url(#flow-arrow)"
              />
              <line
                x1={spoke.x2}
                y1={spoke.y2}
                x2={spoke.x1}
                y2={spoke.y1}
                className="connectivity-edge flow-in"
                markerEnd="url(#flow-arrow)"
              />
            </g>
          )
        })}

        {nodes.map((node, index) => {
          const pos = positions[index]
          const isLit = lit.has(node)
          return (
            <g key={node} className={isLit ? 'connectivity-node lit' : 'connectivity-node'}>
              <circle cx={pos.x} cy={pos.y} r={isLit ? NODE_R_LIT : NODE_R} />
              <text x={pos.x} y={pos.y + 34} textAnchor="middle">
                {node}
              </text>
            </g>
          )
        })}

        <g className="connectivity-core">
          <circle cx={CX} cy={CY} r={CORE_R} />
          <text x={CX} y={CY - 6} textAnchor="middle">
            Lessons
          </text>
          <text x={CX} y={CY + 12} textAnchor="middle">
            Learned
          </text>
        </g>
      </svg>
    </div>
  )
}
