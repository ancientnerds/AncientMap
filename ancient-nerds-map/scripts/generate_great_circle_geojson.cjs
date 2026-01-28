/**
 * Generate GeoJSON with great circle interpolation
 *
 * On a sphere, the shortest path between two points is a great circle arc,
 * not a straight line. This script interpolates points along great circles
 * to ensure lines render correctly on the 3D globe.
 */

const fs = require('fs');
const path = require('path');

/**
 * Interpolate points along a great circle arc between two coordinates.
 * Uses spherical linear interpolation (slerp).
 *
 * @param {number} lon1 - Start longitude
 * @param {number} lat1 - Start latitude
 * @param {number} lon2 - End longitude
 * @param {number} lat2 - End latitude
 * @param {number} numPoints - Number of points to interpolate
 * @returns {Array<[number, number]>} Array of [lon, lat] coordinates
 */
function interpolateGreatCircle(lon1, lat1, lon2, lat2, numPoints = 50) {
  const points = [];
  const toRad = Math.PI / 180;
  const toDeg = 180 / Math.PI;

  const φ1 = lat1 * toRad;
  const λ1 = lon1 * toRad;
  const φ2 = lat2 * toRad;
  const λ2 = lon2 * toRad;

  // Calculate angular distance using haversine
  const dλ = λ2 - λ1;
  const cosφ1 = Math.cos(φ1);
  const cosφ2 = Math.cos(φ2);
  const sinφ1 = Math.sin(φ1);
  const sinφ2 = Math.sin(φ2);

  const d = Math.acos(
    Math.max(-1, Math.min(1,
      sinφ1 * sinφ2 + cosφ1 * cosφ2 * Math.cos(dλ)
    ))
  );

  // Handle case where points are the same or very close
  if (d < 1e-10) {
    return [[lon1, lat1]];
  }

  const sinD = Math.sin(d);

  for (let i = 0; i <= numPoints; i++) {
    const f = i / numPoints;
    const A = Math.sin((1 - f) * d) / sinD;
    const B = Math.sin(f * d) / sinD;

    const x = A * cosφ1 * Math.cos(λ1) + B * cosφ2 * Math.cos(λ2);
    const y = A * cosφ1 * Math.sin(λ1) + B * cosφ2 * Math.sin(λ2);
    const z = A * sinφ1 + B * sinφ2;

    const φ = Math.atan2(z, Math.sqrt(x * x + y * y));
    const λ = Math.atan2(y, x);

    points.push([
      Math.round(λ * toDeg * 10000) / 10000,
      Math.round(φ * toDeg * 10000) / 10000
    ]);
  }

  return points;
}

/**
 * Process a LineString's coordinates with great circle interpolation.
 *
 * @param {Array<[number, number]>} coordinates - Original waypoint coordinates
 * @param {number} pointsPerSegment - Points to interpolate per segment
 * @returns {Array<[number, number]>} Interpolated coordinates
 */
function processLineString(coordinates, pointsPerSegment = 50) {
  if (coordinates.length < 2) return coordinates;

  const result = [];

  for (let i = 0; i < coordinates.length - 1; i++) {
    const [lon1, lat1] = coordinates[i];
    const [lon2, lat2] = coordinates[i + 1];

    const interpolated = interpolateGreatCircle(lon1, lat1, lon2, lat2, pointsPerSegment);

    // Add all points except the last (to avoid duplicates at segment joins)
    if (i < coordinates.length - 2) {
      result.push(...interpolated.slice(0, -1));
    } else {
      // For the last segment, include the endpoint
      result.push(...interpolated);
    }
  }

  return result;
}

/**
 * Process a MultiLineString's coordinates.
 *
 * @param {Array<Array<[number, number]>>} multiCoordinates - Array of LineString coordinates
 * @param {number} pointsPerSegment - Points to interpolate per segment
 * @returns {Array<Array<[number, number]>>} Interpolated coordinates
 */
function processMultiLineString(multiCoordinates, pointsPerSegment = 50) {
  return multiCoordinates.map(coords => processLineString(coords, pointsPerSegment));
}

/**
 * Process a GeoJSON file with great circle interpolation.
 *
 * @param {string} inputPath - Path to input GeoJSON
 * @param {string} outputPath - Path to output GeoJSON
 * @param {number} pointsPerSegment - Points to interpolate per segment
 */
function processGeoJSON(inputPath, outputPath, pointsPerSegment = 50) {
  console.log(`Processing: ${inputPath}`);

  const data = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

  const processedFeatures = data.features.map(feature => {
    const { geometry, ...rest } = feature;

    let newCoordinates;

    if (geometry.type === 'LineString') {
      newCoordinates = processLineString(geometry.coordinates, pointsPerSegment);
      console.log(`  ${feature.properties.name}: ${geometry.coordinates.length} waypoints -> ${newCoordinates.length} points`);
    } else if (geometry.type === 'MultiLineString') {
      newCoordinates = processMultiLineString(geometry.coordinates, pointsPerSegment);
      const totalOriginal = geometry.coordinates.reduce((sum, c) => sum + c.length, 0);
      const totalNew = newCoordinates.reduce((sum, c) => sum + c.length, 0);
      console.log(`  ${feature.properties.name}: ${totalOriginal} waypoints -> ${totalNew} points`);
    } else {
      // Pass through non-line geometries unchanged
      return feature;
    }

    return {
      ...rest,
      geometry: {
        type: geometry.type,
        coordinates: newCoordinates
      }
    };
  });

  const output = {
    type: 'FeatureCollection',
    features: processedFeatures
  };

  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
  console.log(`  Written to: ${outputPath}\n`);
}

// Main execution
const layersDir = path.join(__dirname, '..', 'public', 'data', 'layers');

// Process ley lines
const leyLinesInput = path.join(layersDir, 'ley_lines.geojson');
const leyLinesOutput = path.join(layersDir, 'ley_lines.geojson');

// Process trade routes
const tradeRoutesInput = path.join(layersDir, 'trade_routes.geojson');
const tradeRoutesOutput = path.join(layersDir, 'trade_routes.geojson');

console.log('Great Circle GeoJSON Generator\n');
console.log('================================\n');

if (fs.existsSync(leyLinesInput)) {
  processGeoJSON(leyLinesInput, leyLinesOutput, 50);
}

if (fs.existsSync(tradeRoutesInput)) {
  processGeoJSON(tradeRoutesInput, tradeRoutesOutput, 50);
}

console.log('Done!');
