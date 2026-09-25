/**
 * Layer worker: parses a vector layer file and builds its segment positions off the main
 * thread (coast_detail alone is 9.8 MB of JSON). The main thread fetches through offlineFetch
 * and transfers the bytes in; the Float32Arrays are transferred back out.
 * Created by createLayerParser (vectorRenderer.ts), one per Globe.
 */

import { processLayerRequest, type LayerWorkerRequest } from './segmentBuilder'

self.onmessage = (event: MessageEvent<LayerWorkerRequest>) => {
  const { response, transfer } = processLayerRequest(event.data)
  self.postMessage(response, { transfer })
}
