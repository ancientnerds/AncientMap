declare module 'd3-force-3d' {
  export function forceSimulation(nodes?: object[], numDimensions?: number): any
  export function forceLink(links?: object[]): any
  export function forceManyBody(): any
  export function forceCenter(x?: number, y?: number, z?: number): any
  export function forceX(x?: number | ((node: any) => number)): any
  export function forceY(y?: number | ((node: any) => number)): any
  export function forceCollide(radius?: number | ((node: any) => number)): any
}
