#!/usr/bin/env python3
"""Add 7 new ancient trade routes to trade_routes.geojson"""
import json
import math
import os


def interp(p1, p2, n):
    """Linearly interpolate n points between p1 and p2 (exclusive of endpoints)."""
    pts = []
    for i in range(1, n + 1):
        t = i / (n + 1)
        lon = p1[0] + t * (p2[0] - p1[0])
        lat = p1[1] + t * (p2[1] - p1[1])
        pts.append([round(lon, 4), round(lat, 4)])
    return pts


def interpolate_path(waypoints, total_target):
    """Given a list of waypoints, interpolate to ~total_target points total."""
    # Calculate total distance to distribute points proportionally
    segments = []
    total_dist = 0
    for i in range(len(waypoints) - 1):
        dx = waypoints[i + 1][0] - waypoints[i][0]
        dy = waypoints[i + 1][1] - waypoints[i][1]
        d = math.sqrt(dx * dx + dy * dy)
        segments.append(d)
        total_dist += d

    # Distribute extra points proportionally to segment length
    extra_points = total_target - len(waypoints)
    if extra_points <= 0:
        return [[round(w[0], 4), round(w[1], 4)] for w in waypoints]

    result = [[round(waypoints[0][0], 4), round(waypoints[0][1], 4)]]
    for i in range(len(segments)):
        # How many interpolated points for this segment
        n = max(0, round(extra_points * segments[i] / total_dist))
        result.extend(interp(waypoints[i], waypoints[i + 1], n))
        result.append([round(waypoints[i + 1][0], 4), round(waypoints[i + 1][1], 4)])

    return result


def maritime_silk_road():
    """Maritime Silk Road: Guangzhou -> Vietnam coast -> Malacca -> Sri Lanka ->
    Kerala -> Arabian Sea -> Aden -> Red Sea -> Egyptian ports. ~300 points."""
    waypoints = [
        # Guangzhou (Canton)
        [113.25, 23.13],
        # South along Chinese coast
        [112.5, 22.3],
        [111.3, 21.5],
        [110.4, 20.9],
        [109.5, 20.4],
        # Hainan Island north coast
        [109.1, 20.0],
        [108.6, 19.5],
        # Into Gulf of Tonkin
        [108.2, 19.0],
        [107.8, 18.2],
        [107.5, 17.3],
        # Vietnam coast - heading south
        [107.1, 16.5],
        [108.0, 16.1],
        [108.5, 15.5],
        [108.9, 14.8],
        [109.1, 14.0],
        [109.2, 13.2],
        [109.0, 12.3],
        [108.6, 11.5],
        [108.0, 10.8],
        # Rounding southern Vietnam / Mekong Delta
        [107.0, 10.3],
        [106.5, 9.8],
        [105.8, 9.3],
        [105.0, 8.8],
        # Across Gulf of Thailand towards Malay Peninsula
        [104.0, 8.0],
        [103.5, 7.0],
        [103.0, 5.5],
        [102.8, 4.5],
        [102.5, 3.5],
        # Through Strait of Malacca
        [102.0, 2.8],
        [101.5, 2.3],
        [101.0, 2.0],
        [100.5, 2.2],
        [100.0, 2.5],
        [99.5, 3.0],
        [99.0, 3.5],
        [98.5, 3.8],
        [98.0, 4.5],
        [97.5, 5.0],
        # Exiting Malacca Strait into Indian Ocean
        [96.5, 5.5],
        [95.5, 6.0],
        [94.0, 6.5],
        # Across Bay of Bengal / Andaman Sea
        [92.0, 7.0],
        [90.0, 7.2],
        [88.0, 7.3],
        [86.0, 7.2],
        [84.0, 7.0],
        # Approaching Sri Lanka
        [82.5, 7.0],
        [81.5, 7.2],
        # Sri Lanka (Colombo area)
        [80.5, 7.0],
        [79.9, 6.9],
        # Heading northwest to Kerala / Muziris
        [79.0, 7.5],
        [77.5, 8.5],
        [76.5, 9.5],
        # Muziris / Kerala coast
        [76.2, 10.0],
        [75.8, 10.5],
        [75.5, 11.0],
        # Across Arabian Sea
        [74.0, 11.5],
        [72.0, 12.0],
        [70.0, 12.5],
        [68.0, 13.0],
        [66.0, 13.2],
        [64.0, 13.5],
        [62.0, 13.5],
        [60.0, 13.5],
        [58.0, 13.5],
        [56.0, 13.3],
        [54.0, 13.0],
        [52.5, 12.8],
        # Approaching Aden / Yemen coast
        [50.0, 12.5],
        [48.0, 12.5],
        [46.0, 12.6],
        # Aden
        [45.0, 12.8],
        # Bab el-Mandeb Strait
        [44.0, 12.7],
        [43.5, 12.8],
        [43.3, 13.0],
        # Into the Red Sea
        [43.2, 13.5],
        [43.0, 14.0],
        [42.8, 14.5],
        [42.5, 15.0],
        [42.2, 15.5],
        [41.8, 16.0],
        [41.3, 16.5],
        [40.8, 17.0],
        [40.3, 17.5],
        [39.8, 18.0],
        [39.3, 18.5],
        [38.8, 19.0],
        [38.3, 19.5],
        [37.8, 20.0],
        [37.3, 20.5],
        [36.8, 21.0],
        [36.3, 21.5],
        [36.0, 22.0],
        [35.8, 22.5],
        [35.5, 23.0],
        [35.3, 23.5],
        [35.2, 24.0],
        [35.0, 24.5],
        [34.8, 25.0],
        [34.7, 25.5],
        # Berenice / Myos Hormos area
        [34.5, 26.0],
        [34.3, 26.5],
    ]
    return interpolate_path(waypoints, 300)


def phoenician_sea_routes():
    """Phoenician Sea Routes: Tyre/Sidon -> Cyprus -> Rhodes -> Crete -> Malta ->
    Sicily -> Sardinia -> Ibiza -> Spanish coast to Cadiz. Branch from Carthage.
    MultiLineString with ~250 points total."""

    # Main route: Tyre -> Cadiz
    main_waypoints = [
        # Tyre / Sidon (Lebanon coast)
        [35.2, 33.27],
        [35.0, 33.5],
        # Heading to Cyprus
        [34.5, 33.8],
        [34.0, 34.2],
        [33.5, 34.5],
        # Cyprus (south coast)
        [33.0, 34.6],
        [32.5, 34.7],
        [32.0, 34.65],
        # West from Cyprus toward Turkey south coast
        [31.5, 34.6],
        [31.0, 34.7],
        [30.5, 35.0],
        [30.0, 35.3],
        [29.5, 35.6],
        [29.0, 35.8],
        # Rhodes
        [28.2, 36.4],
        [27.8, 36.3],
        # Through Aegean south
        [27.0, 36.0],
        [26.5, 35.8],
        [26.0, 35.5],
        # Crete (east to west)
        [25.5, 35.3],
        [25.0, 35.2],
        [24.5, 35.2],
        [24.0, 35.3],
        [23.5, 35.5],
        # West of Crete into open Mediterranean
        [23.0, 35.5],
        [22.0, 35.5],
        [21.0, 35.6],
        [20.0, 35.7],
        [19.0, 35.8],
        [18.0, 35.9],
        [17.0, 35.9],
        [16.0, 35.8],
        # Malta
        [15.0, 35.9],
        [14.5, 35.9],
        # Sicily (south coast)
        [14.0, 36.7],
        [13.5, 37.0],
        [13.0, 37.5],
        [12.5, 37.8],
        # Heading through Tyrrhenian Sea toward Sardinia
        [12.0, 38.0],
        [11.5, 38.3],
        [11.0, 38.5],
        [10.5, 38.8],
        [10.0, 39.0],
        # Sardinia (south/west coast)
        [9.5, 39.2],
        [9.0, 39.0],
        [8.5, 38.8],
        [8.3, 39.0],
        [8.2, 39.5],
        [8.3, 40.0],
        # Heading west from Sardinia
        [7.5, 39.8],
        [6.5, 39.5],
        [5.5, 39.3],
        [4.5, 39.2],
        [3.5, 39.0],
        # Ibiza / Balearics
        [2.5, 39.0],
        [1.5, 39.0],
        [1.0, 38.9],
        # Along Spanish coast heading south
        [0.5, 38.5],
        [0.0, 38.0],
        [-0.5, 37.5],
        [-1.0, 37.0],
        [-1.5, 36.8],
        [-2.0, 36.7],
        [-2.5, 36.7],
        [-3.0, 36.7],
        [-3.5, 36.6],
        [-4.0, 36.5],
        [-4.5, 36.3],
        [-5.0, 36.2],
        [-5.5, 36.1],
        # Strait of Gibraltar / Cadiz (Gadir)
        [-6.0, 36.4],
        [-6.3, 36.5],
    ]

    # Branch from Carthage (Tunis) connecting to main route near Sicily
    branch_waypoints = [
        # Carthage (modern Tunis)
        [10.3, 36.85],
        [10.5, 36.9],
        [10.8, 37.0],
        [11.0, 37.0],
        [11.5, 37.0],
        [12.0, 37.0],
        [12.5, 37.0],
        # Meets main route near Sicily area
        [13.0, 37.0],
        [13.5, 37.0],
    ]

    main_coords = interpolate_path(main_waypoints, 210)
    branch_coords = interpolate_path(branch_waypoints, 40)
    return main_coords, branch_coords


def lapis_lazuli_route():
    """Lapis Lazuli Route: Badakhshan (NE Afghanistan) -> Hindu Kush passes ->
    Iranian Plateau -> Mesopotamia (Ur/Babylon) -> Egypt (Memphis). ~200 points."""
    waypoints = [
        # Badakhshan, NE Afghanistan (lapis lazuli mines)
        [70.8, 36.7],
        # Descend through Hindu Kush passes
        [70.3, 36.5],
        [70.0, 36.2],
        [69.5, 35.9],
        [69.2, 35.5],
        [69.0, 35.2],
        [68.7, 34.9],
        # Kabul area
        [68.5, 34.7],
        [68.3, 34.5],
        # South through passes toward Kandahar direction
        [67.8, 34.2],
        [67.3, 33.8],
        [66.8, 33.5],
        [66.2, 33.2],
        [65.5, 33.0],
        # Across into Iran (Herat direction then south)
        [64.8, 33.2],
        [64.0, 33.5],
        [63.2, 33.8],
        # Herat area
        [62.2, 34.3],
        [61.5, 34.5],
        # Southwest across Iranian plateau
        [60.5, 34.2],
        [59.5, 33.8],
        [58.5, 33.5],
        [57.5, 33.2],
        [56.5, 33.0],
        [55.5, 32.8],
        # Central Iran
        [54.5, 32.6],
        [53.5, 32.8],
        [52.5, 33.0],
        [51.5, 33.2],
        [50.5, 33.3],
        # Western Iran / Zagros Mountains passes
        [49.5, 33.3],
        [48.8, 33.2],
        [48.0, 33.0],
        [47.5, 32.8],
        [47.0, 32.5],
        [46.5, 32.3],
        # Entering Mesopotamia
        [46.0, 32.2],
        [45.5, 32.0],
        [45.0, 31.8],
        # Babylon area
        [44.5, 32.5],
        [44.4, 32.3],
        [44.3, 32.0],
        # South to Ur
        [44.2, 31.5],
        [44.0, 31.0],
        # Along Euphrates northwest
        [43.5, 31.5],
        [43.0, 32.0],
        [42.5, 32.5],
        [42.0, 33.0],
        [41.5, 33.5],
        [41.0, 34.0],
        [40.5, 34.5],
        # Across northern Syria
        [40.0, 35.0],
        [39.5, 35.5],
        [39.0, 36.0],
        [38.5, 36.2],
        [38.0, 36.4],
        [37.5, 36.5],
        [37.0, 36.4],
        [36.5, 36.2],
        # Mediterranean coast / Levant
        [36.0, 35.8],
        [35.8, 35.5],
        [35.5, 35.0],
        [35.3, 34.5],
        [35.0, 34.0],
        [34.8, 33.5],
        [34.5, 33.0],
        # Down coast toward Egypt
        [34.2, 32.5],
        [34.0, 32.0],
        [33.8, 31.5],
        [33.5, 31.3],
        [33.0, 31.1],
        [32.5, 31.0],
        [32.0, 30.8],
        [31.5, 30.5],
        # Memphis / Cairo area
        [31.2, 30.0],
    ]
    return interpolate_path(waypoints, 200)


def route_to_punt():
    """Egyptian Route to Punt: Red Sea ports (Quseir/Berenice) -> south along Red Sea
    coast -> Bab el-Mandeb -> Horn of Africa coast. ~200 points."""
    waypoints = [
        # Quseir area (Egyptian Red Sea port)
        [34.3, 26.1],
        [34.4, 25.8],
        [34.5, 25.5],
        [34.6, 25.2],
        [34.7, 24.9],
        # Berenice
        [35.0, 24.5],
        [35.2, 24.0],
        [35.4, 23.5],
        [35.6, 23.0],
        [35.8, 22.5],
        [36.0, 22.0],
        [36.3, 21.5],
        [36.5, 21.0],
        [36.8, 20.5],
        [37.2, 20.0],
        [37.5, 19.5],
        [37.8, 19.0],
        [38.2, 18.5],
        [38.5, 18.0],
        [38.8, 17.5],
        [39.2, 17.0],
        [39.5, 16.5],
        [39.8, 16.0],
        [40.2, 15.5],
        [40.5, 15.0],
        # Approaching Eritrean coast
        [40.8, 14.5],
        [41.2, 14.0],
        [41.5, 13.5],
        [42.0, 13.0],
        # Bab el-Mandeb Strait
        [42.5, 12.8],
        [43.0, 12.6],
        [43.3, 12.5],
        # Rounding into Gulf of Aden
        [43.5, 12.3],
        [43.8, 12.0],
        [44.0, 11.8],
        [44.5, 11.5],
        [45.0, 11.3],
        [45.5, 11.2],
        # Djibouti / Somalia area (Land of Punt region)
        [46.0, 11.0],
        [46.5, 10.8],
        [47.0, 10.5],
        [47.5, 10.2],
        [48.0, 10.0],
        [48.5, 9.8],
        # Along Somali coast
        [49.0, 9.5],
        [49.5, 9.0],
        [50.0, 8.5],
    ]
    return interpolate_path(waypoints, 200)


def via_regia():
    """Via Regia: Frankfurt -> Erfurt -> Leipzig -> Wroclaw -> Krakow -> Lviv -> Kyiv.
    ~200 points following the historic east-west route across Central Europe."""
    waypoints = [
        # Frankfurt am Main
        [8.68, 50.11],
        [8.9, 50.1],
        [9.2, 50.1],
        [9.5, 50.1],
        [9.8, 50.15],
        [10.0, 50.2],
        [10.3, 50.3],
        [10.5, 50.4],
        [10.7, 50.5],
        # Erfurt
        [10.98, 50.98],
        [11.2, 51.0],
        [11.5, 51.1],
        [11.8, 51.2],
        [12.0, 51.3],
        # Leipzig
        [12.37, 51.34],
        [12.6, 51.3],
        [12.9, 51.25],
        [13.2, 51.2],
        [13.5, 51.15],
        [13.8, 51.1],
        [14.1, 51.1],
        [14.4, 51.1],
        [14.7, 51.1],
        [15.0, 51.1],
        [15.3, 51.1],
        [15.6, 51.1],
        [15.9, 51.1],
        [16.2, 51.1],
        [16.5, 51.1],
        # Wroclaw
        [17.03, 51.1],
        [17.3, 51.05],
        [17.6, 51.0],
        [17.9, 50.9],
        [18.2, 50.8],
        [18.5, 50.7],
        [18.8, 50.6],
        [19.1, 50.5],
        [19.4, 50.3],
        [19.7, 50.15],
        # Krakow
        [19.94, 50.06],
        [20.2, 50.0],
        [20.5, 50.0],
        [20.8, 50.0],
        [21.1, 50.0],
        [21.4, 50.0],
        [21.7, 50.0],
        [22.0, 49.9],
        [22.3, 49.85],
        [22.6, 49.8],
        [22.9, 49.8],
        [23.2, 49.8],
        [23.5, 49.8],
        # Lviv
        [24.0, 49.84],
        [24.3, 49.9],
        [24.6, 50.0],
        [25.0, 50.1],
        [25.5, 50.2],
        [26.0, 50.3],
        [26.5, 50.3],
        [27.0, 50.35],
        [27.5, 50.35],
        [28.0, 50.4],
        [28.5, 50.4],
        [29.0, 50.4],
        [29.5, 50.4],
        [30.0, 50.4],
        # Kyiv
        [30.52, 50.45],
    ]
    return interpolate_path(waypoints, 200)


def salt_road():
    """Salt Road: Taghaza salt mines (northern Sahara) -> south through desert ->
    Timbuktu -> Djenne/Niger River. ~150 points."""
    waypoints = [
        # Taghaza salt mines
        [-3.0, 23.5],
        [-3.0, 23.0],
        [-3.0, 22.5],
        [-3.0, 22.0],
        [-3.0, 21.5],
        [-3.0, 21.0],
        [-3.0, 20.5],
        [-3.0, 20.0],
        [-3.0, 19.5],
        [-3.0, 19.0],
        [-3.1, 18.5],
        [-3.1, 18.0],
        [-3.1, 17.5],
        [-3.1, 17.0],
        # Timbuktu
        [-3.0, 16.77],
        # Continue south toward Djenne along Niger River
        [-3.1, 16.5],
        [-3.2, 16.2],
        [-3.3, 15.9],
        [-3.5, 15.6],
        [-3.7, 15.3],
        [-3.9, 15.0],
        [-4.0, 14.8],
        [-4.1, 14.5],
        [-4.2, 14.2],
        # Djenne
        [-4.55, 13.9],
    ]
    return interpolate_path(waypoints, 150)


def grand_trunk_road():
    """Grand Trunk Road: Pataliputra/Patna -> Varanasi -> Kanpur -> Agra -> Delhi ->
    Lahore -> Peshawar -> Khyber Pass -> Kabul. ~250 points."""
    waypoints = [
        # Pataliputra / Patna
        [85.1, 25.6],
        [84.8, 25.55],
        [84.5, 25.5],
        [84.2, 25.45],
        [83.9, 25.4],
        [83.6, 25.35],
        [83.3, 25.3],
        # Varanasi
        [83.0, 25.32],
        [82.7, 25.35],
        [82.4, 25.4],
        [82.1, 25.5],
        [81.8, 25.55],
        [81.5, 25.6],
        [81.2, 25.7],
        [80.9, 25.8],
        [80.6, 25.9],
        [80.3, 26.0],
        # Kanpur
        [80.35, 26.45],
        [80.0, 26.6],
        [79.6, 26.7],
        [79.2, 26.8],
        [78.8, 26.95],
        [78.5, 27.05],
        [78.2, 27.12],
        # Agra
        [78.02, 27.18],
        [77.7, 27.3],
        [77.4, 27.5],
        [77.2, 27.7],
        [77.1, 27.9],
        [77.0, 28.1],
        [77.0, 28.3],
        [77.1, 28.5],
        # Delhi
        [77.21, 28.61],
        # Delhi -> NW through Haryana/Punjab toward Lahore
        [77.0, 28.7],
        [76.8, 28.85],
        [76.6, 29.0],
        [76.4, 29.15],
        [76.2, 29.3],
        [76.0, 29.5],
        [75.8, 29.7],
        [75.6, 29.85],
        [75.4, 30.0],
        # Across Punjab (Ambala -> Ludhiana -> Amritsar direction)
        [75.2, 30.2],
        [75.0, 30.4],
        [74.8, 30.6],
        [74.6, 30.8],
        [74.5, 31.0],
        [74.4, 31.2],
        [74.35, 31.4],
        # Lahore
        [74.35, 31.55],
        # Lahore -> NW toward Peshawar (following Indus/GT Road)
        [74.0, 31.7],
        [73.6, 31.9],
        [73.2, 32.1],
        [72.8, 32.4],
        [72.5, 32.6],
        [72.2, 32.8],
        [72.0, 33.0],
        [71.8, 33.3],
        [71.6, 33.6],
        [71.5, 33.8],
        # Peshawar
        [71.5, 34.0],
        # Khyber Pass
        [71.2, 34.1],
        [70.9, 34.2],
        [70.6, 34.3],
        [70.3, 34.35],
        [70.0, 34.4],
        [69.8, 34.45],
        [69.5, 34.5],
        # Kabul
        [69.17, 34.53],
    ]
    return interpolate_path(waypoints, 250)


def create_routes():
    """Generate the 7 new route features."""
    routes = []

    # 1. Maritime Silk Road
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Maritime Silk Road",
            "era": "2nd c. BC \u2013 500 AD",
            "type": "sea",
            "description": "Maritime trade network linking China, Southeast Asia, India, Arabia, and Egypt via coastal and oceanic routes"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": maritime_silk_road()
        }
    })

    # 2. Phoenician Sea Routes (MultiLineString due to branch)
    main_coords, branch_coords = phoenician_sea_routes()
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Phoenician Sea Routes",
            "era": "1500 BC \u2013 300 BC",
            "type": "sea",
            "description": "Phoenician maritime network across the Mediterranean from Tyre to Cadiz, with a branch from Carthage"
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [main_coords, branch_coords]
        }
    })

    # 3. Lapis Lazuli Route
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Lapis Lazuli Route",
            "era": "3000 BC \u2013 500 BC",
            "type": "land",
            "description": "Ancient trade route carrying lapis lazuli from Afghan mines through Iran to Mesopotamia and Egypt"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": lapis_lazuli_route()
        }
    })

    # 4. Egyptian Route to Punt
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Egyptian Route to Punt",
            "era": "2500 BC \u2013 1100 BC",
            "type": "sea",
            "description": "Egyptian maritime expeditions down the Red Sea to the legendary Land of Punt for incense, gold, and exotic goods"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": route_to_punt()
        }
    })

    # 5. Via Regia
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Via Regia",
            "era": "Bronze Age \u2013 Roman",
            "type": "land",
            "description": "Major east-west trade and travel route across Central Europe from Frankfurt to Kyiv"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": via_regia()
        }
    })

    # 6. Salt Road
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Salt Road (Trans-Saharan)",
            "era": "Bronze Age \u2013 Roman",
            "type": "land",
            "description": "Trade route carrying Saharan salt from Taghaza mines south through the desert to Timbuktu and the Niger River"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": salt_road()
        }
    })

    # 7. Grand Trunk Road
    routes.append({
        "type": "Feature",
        "properties": {
            "name": "Grand Trunk Road",
            "era": "3rd c. BC \u2013 500 AD",
            "type": "land",
            "description": "Ancient highway across the Indian subcontinent from Pataliputra through Delhi and the Khyber Pass to Kabul"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": grand_trunk_road()
        }
    })

    return routes


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    path = os.path.join(project_root, 'ancient-nerds-map', 'public', 'data', 'layers', 'trade_routes.geojson')

    with open(path) as f:
        data = json.load(f)

    print(f'Existing routes: {len(data["features"])}')

    new_routes = create_routes()
    data['features'].extend(new_routes)

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'Total routes after addition: {len(data["features"])}')
    print()
    for i, feat in enumerate(data['features']):
        props = feat['properties']
        geom = feat['geometry']
        if geom['type'] == 'MultiLineString':
            total_pts = sum(len(line) for line in geom['coordinates'])
        else:
            total_pts = len(geom['coordinates'])
        print(f'  {i + 1:2d}. {props["name"]} ({props["type"]}, {props["era"]}) - {geom["type"]}, {total_pts} pts')


if __name__ == '__main__':
    main()
