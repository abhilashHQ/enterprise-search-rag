const GRID = [
  "............",
  "..###.####..",
  ".#...#....#.",
  "#..#.#.##..#",
  "#.#..#...#.#",
  "#...A#.A...#",
  "#.##.#..##.#",
  "#....#.A...#",
  ".#..#.#...#.",
  "..##...###..",
  ".......##...",
  "........#...",
]

const CELLS = GRID.flatMap((row, y) =>
  [...row].flatMap((c, x) => (c === "." ? [] : [{ x, y, fill: c === "A" ? "#2f9bff" : "#111111" }])),
)

export function PixelLogo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 12 12"
      width={size}
      height={size}
      shapeRendering="crispEdges"
      className={className}
      aria-hidden
    >
      {CELLS.map((c) => (
        <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width={1} height={1} fill={c.fill} />
      ))}
    </svg>
  )
}
