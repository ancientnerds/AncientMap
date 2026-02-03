"""
Transform Maps with GCPs - Compute Affine Transformations

This script processes the Stanford georeferenced maps dataset and computes
affine transformation matrices from Ground Control Points (GCPs).

The affine transformation allows precise conversion from geographic coordinates
(lat/lon) to pixel coordinates on the map image.

Output: ancient_maps.json with transformation coefficients for precise marker placement.
"""

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


def compute_affine_transform(gcps: list) -> tuple:
    """
    Compute affine transformation coefficients from GCPs.

    The transformation converts (lon, lat) -> (pixel_x, pixel_y):
        pixel_x = a * lon + b * lat + c
        pixel_y = d * lon + e * lat + f

    Args:
        gcps: List of dicts with 'location' [lon, lat] and 'pixel' [x, y]

    Returns:
        Tuple of (transform_coeffs, image_size_estimate)
        transform_coeffs: [a, b, c, d, e, f]
        image_size_estimate: [width, height] based on max pixel values
    """
    if not gcps or len(gcps) < 3:
        return None, None

    # Extract coordinates
    geo_coords = np.array([[p['location'][0], p['location'][1]] for p in gcps])
    pixel_coords = np.array([[p['pixel'][0], p['pixel'][1]] for p in gcps])

    # Build matrix A where each row is [lon, lat, 1]
    A = np.column_stack([geo_coords, np.ones(len(gcps))])

    try:
        # Solve least squares for pixel_x = a*lon + b*lat + c
        coeffs_x, _, _, _ = np.linalg.lstsq(A, pixel_coords[:, 0], rcond=None)
        # Solve least squares for pixel_y = d*lon + e*lat + f
        coeffs_y, _, _, _ = np.linalg.lstsq(A, pixel_coords[:, 1], rcond=None)

        # Combine into single array [a, b, c, d, e, f]
        transform = [float(x) for x in list(coeffs_x) + list(coeffs_y)]

        # Estimate image size from max pixel coordinates (add 10% margin)
        max_x = max(p['pixel'][0] for p in gcps)
        max_y = max(p['pixel'][1] for p in gcps)
        img_size = [int(max_x * 1.1), int(max_y * 1.1)]

        return transform, img_size
    except Exception as e:
        print(f"Error computing transform: {e}")
        return None, None


def compute_bbox(gcps: list) -> list:
    """Compute bounding box from GCPs."""
    if not gcps:
        return None
    lons = [p['location'][0] for p in gcps]
    lats = [p['location'][1] for p in gcps]
    return [
        round(min(lons), 3),
        round(min(lats), 3),
        round(max(lons), 3),
        round(max(lats), 3)
    ]


def process_maps():
    """Process Stanford dataset and create JSON with affine transforms."""

    csv_path = Path('data/raw/stanford_georef/luna_omo_metadata_56628_20220724.csv')
    output_path = Path('ancient-nerds-map/public/data/ancient_maps.json')

    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"Total maps: {len(df)}")

    maps_data = []
    processed = 0
    with_transform = 0

    for idx, row in df.iterrows():
        if idx % 5000 == 0:
            print(f"Processing {idx}/{len(df)}...")

        # Parse GCPs
        gcps_str = row.get('gcps')
        if pd.isna(gcps_str):
            continue

        try:
            gcps = ast.literal_eval(gcps_str)
        except:
            continue

        if not gcps or len(gcps) < 3:
            continue

        # Compute bbox from GCPs
        bbox = compute_bbox(gcps)
        if not bbox:
            continue

        # Get image URLs
        thumbnail = row.get('urlSize1', row.get('urlSize2', ''))
        full_image = row.get('urlSize4', '')
        if pd.isna(thumbnail) or not thumbnail:
            thumbnail = full_image
        if pd.isna(full_image) or not full_image:
            continue

        # Compute affine transformation
        transform, img_size = compute_affine_transform(gcps)

        # Parse date
        try:
            date = int(float(row['date'])) if pd.notna(row['date']) else None
        except:
            date = None

        # Build map data with compact keys
        map_data = {
            'id': str(row.get('id', idx))[:36],
            't': str(row.get('title', ''))[:100],  # title
            'd': date,  # date
            'c': str(row.get('creator', ''))[:60] if pd.notna(row.get('creator')) else '',  # creator
            'th': str(thumbnail),  # thumbnail
            'f': str(full_image),  # full image
            'u': str(row.get('link_url', '')) if pd.notna(row.get('link_url')) else '',  # url
            'b': bbox,  # bounding box
        }

        # Add transformation if computed successfully
        if transform and img_size:
            # Round transform coefficients for smaller file size
            map_data['tr'] = [round(x, 4) for x in transform]
            map_data['sz'] = img_size
            with_transform += 1

        maps_data.append(map_data)
        processed += 1

    print(f"\nProcessed: {processed} maps")
    print(f"With transforms: {with_transform} maps")

    # Sort by date
    maps_data.sort(key=lambda x: x.get('d') or 9999)

    # Save to JSON
    output = {
        'm': maps_data,
        'meta': {
            'src': 'David Rumsey Collection',
            'n': len(maps_data),
            'withTransform': with_transform,
            'generated': datetime.now(UTC).isoformat()
        }
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, separators=(',', ':'))

    file_size = output_path.stat().st_size / 1024 / 1024
    print(f"\nSaved to {output_path}")
    print(f"File size: {file_size:.2f} MB")

    # Show sample
    if maps_data:
        print("\nSample map:")
        sample = maps_data[0]
        print(f"  Title: {sample['t']}")
        print(f"  Date: {sample['d']}")
        print(f"  Bbox: {sample['b']}")
        if 'tr' in sample:
            print(f"  Transform: {sample['tr']}")
            print(f"  Image size: {sample['sz']}")


if __name__ == '__main__':
    process_maps()
