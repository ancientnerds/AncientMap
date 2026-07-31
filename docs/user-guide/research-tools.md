# Proximity and measurement tools

[← Guide contents](README.md)

## Proximity search

The **Proximity** tab finds mapped sites within a circular distance of a chosen point.

### Set the centre

Choose one method:

- **My location** estimates your position. Depending on browser support and network conditions, this may use device or approximate IP-based location.
- **Set on globe** lets you click the desired point.
- Enter or paste coordinates into the coordinate field.
- In an open site record, use **Search nearby sites** beside the coordinates.

The coordinate parser accepts common decimal and directional formats. Always check the displayed N/S and E/W values before interpreting the results.

### Set the radius

Move the radius slider from 10 km to 2,000 km. Results are calculated as great-circle distance around the Earth, rather than as road or walking distance.

The result list shows sites within the circle. A proximity centre can also be used with a name search by enabling **Within proximity** in the **Search** tab.

Use **Clear proximity filter** when finished. Switching tabs alone does not remove the circle.

### Research cautions

- Device location can be approximate.
- A site’s stored coordinate may represent a monument, settlement centre, dataset centroid, or generalized protected location.
- Coastal and submerged-site analysis should account for changing shorelines and coordinate precision.

## Measure distance

The **Measure** tab calculates great-circle distance between two points.

1. Choose **km** or **mi**.
2. Enable **Snap to sites** if endpoints should attach to nearby site markers.
3. Click the first point on the globe.
4. Click the second point.
5. Read the result in the measurement list.

Each completed line receives a colour and sequence number. Select a measurement in the list to highlight it. Delete an individual measurement with its delete button, or clear all measurements from the list header.

With **Snap to sites** enabled, the list identifies endpoints as `site`; otherwise they are shown as `coord`. Zoom in before snapping in dense areas so the intended marker is unambiguous.

## What the measurement does not represent

The displayed value is a direct surface distance between coordinates. It does not model:

- terrain or elevation;
- historical roads or sea routes;
- obstacles and navigable passages;
- uncertainty in the site coordinates;
- the historical shape of coastlines.

Use the result as a geographic baseline, then interpret travel or exchange using the relevant terrain, river, route, empire, and paleogeographic layers.

