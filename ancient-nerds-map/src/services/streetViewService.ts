/**
 * Street View Service
 *
 * Generates embed URLs for Street View panoramas.
 */

/**
 * Generate the embed URL for Street View iframe.
 */
export function getStreetViewEmbedUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/embed?pb=!4v1!6m8!1m7!1e1!2m2!1d${lat}!2d${lon}!3f0!4f0!5f0.7`
}
