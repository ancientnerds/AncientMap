#!/usr/bin/env python3
"""Quick test of fixed ingesters."""

import sys
sys.path.insert(0, ".")

def test_open_context():
    """Test Open Context with new API."""
    print("\n" + "=" * 50)
    print("Testing Open Context")
    print("=" * 50)

    import httpx
    url = "https://opencontext.org/query/.json"
    params = {"rows": 5, "type": "subjects", "response": "geo-record"}
    headers = {"User-Agent": "oc-api-client"}

    r = httpx.get(url, params=params, headers=headers, follow_redirects=True, timeout=60)
    print(f"Status: {r.status_code}")
    data = r.json()
    features = data.get("features", [])
    print(f"Features: {len(features)}")
    if features:
        f = features[0]
        print(f"  Label: {f.get('label')}")
        print(f"  Geometry: {f.get('geometry', {}).get('type')}")
    return len(features) > 0


def test_wikidata():
    """Test Wikidata with simple query."""
    print("\n" + "=" * 50)
    print("Testing Wikidata")
    print("=" * 50)

    import httpx
    query = """
    SELECT ?item ?itemLabel ?coord WHERE {
      ?item wdt:P31 wd:Q839954 .
      ?item wdt:P625 ?coord .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
    }
    LIMIT 5
    """
    url = "https://query.wikidata.org/sparql"
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "AncientNerds/1.0 (Research Platform; https://ancientnerds.com; contact@ancientnerds.com) Python/httpx",
    }

    r = httpx.get(url, params={"query": query}, headers=headers, timeout=120)
    print(f"Status: {r.status_code}")
    data = r.json()
    bindings = data.get("results", {}).get("bindings", [])
    print(f"Results: {len(bindings)}")
    if bindings:
        b = bindings[0]
        print(f"  Item: {b.get('itemLabel', {}).get('value')}")
        print(f"  Coord: {b.get('coord', {}).get('value')[:50]}...")
    return len(bindings) > 0


def test_arachne():
    """Test Arachne with search."""
    print("\n" + "=" * 50)
    print("Testing Arachne")
    print("=" * 50)

    import httpx
    url = "https://arachne.dainst.org/data/search"
    params = {"q": "temple", "limit": 5}
    headers = {"Accept": "application/json", "User-Agent": "AncientNerds/1.0 (Research Platform)"}

    r = httpx.get(url, params=params, headers=headers, timeout=60)
    print(f"Status: {r.status_code}")
    data = r.json()
    entities = data.get("entities", [])
    print(f"Entities: {len(entities)}")
    with_coords = [e for e in entities if e.get("places")]
    print(f"With coordinates: {len(with_coords)}")
    if with_coords:
        e = with_coords[0]
        loc = e["places"][0].get("location", {})
        print(f"  Title: {e.get('title')[:50]}...")
        print(f"  Coords: {loc.get('lat')}, {loc.get('lon')}")
    return len(with_coords) > 0


def test_scotland():
    """Test Scotland with objectIds."""
    print("\n" + "=" * 50)
    print("Testing Scotland HES")
    print("=" * 50)

    import httpx
    url = "https://inspire.hes.scot/arcgis/rest/services/INSPIRE/Scottish_Cultural_ProtectedSites/MapServer/3/query"

    # First get objectIds
    params = {"where": "1=1", "returnIdsOnly": "true", "f": "json"}
    r = httpx.get(url, params=params, timeout=60)
    print(f"Status: {r.status_code}")
    data = r.json()
    object_ids = data.get("objectIds", [])
    print(f"ObjectIds: {len(object_ids)}")

    if object_ids:
        # Fetch first 5
        ids_str = ",".join(str(id) for id in object_ids[:5])
        params2 = {"objectIds": ids_str, "outFields": "*", "outSR": "4326", "f": "json"}
        r2 = httpx.get(url, params=params2, timeout=60)
        print(f"Features status: {r2.status_code}")
        data2 = r2.json()
        features = data2.get("features", [])
        print(f"Features: {len(features)}")
        if features:
            f = features[0]
            attrs = f.get("attributes", {})
            geom = f.get("geometry", {})
            print(f"  Name: {attrs.get('NAME', attrs.get('Name', 'N/A'))[:50]}")
            print(f"  Geometry: x={geom.get('x')}, y={geom.get('y')}")
        return len(features) > 0
    return False


def test_eamena():
    """Test EAMENA LDP API."""
    print("\n" + "=" * 50)
    print("Testing EAMENA")
    print("=" * 50)

    import httpx
    headers = {"Accept": "application/json", "User-Agent": "AncientNerds/1.0 (Research Platform)"}

    # Get resources list
    r = httpx.get("https://database.eamena.org/resources/", headers=headers, timeout=60)
    print(f"Status: {r.status_code}")
    data = r.json()
    uris = data.get("ldp:contains", [])
    print(f"Resource URIs: {len(uris)}")

    if uris:
        # Fetch first resource
        uri = uris[0]
        r2 = httpx.get(uri, headers=headers, timeout=30)
        print(f"Resource status: {r2.status_code}")
        if r2.status_code == 200:
            data2 = r2.json()
            print(f"  Name: {data2.get('displayname')}")
            resource = data2.get("resource", {})
            geometry = resource.get("Geometry", [])
            print(f"  Has geometry: {len(geometry) > 0}")
        return r2.status_code == 200
    return False


def test_p3k14c():
    """Test P3k14c via Open Context."""
    print("\n" + "=" * 50)
    print("Testing P3k14c (via Open Context)")
    print("=" * 50)

    import httpx
    url = "https://opencontext.org/query/.json"
    params = {
        "proj": "cdd78c10-e6da-42ef-9829-e792ce55bdd6",
        "rows": 5,
        "response": "geo-record"
    }
    headers = {"User-Agent": "oc-api-client"}

    r = httpx.get(url, params=params, headers=headers, follow_redirects=True, timeout=60)
    print(f"Status: {r.status_code}")
    data = r.json()
    features = data.get("features", [])
    print(f"Features: {len(features)}")
    if features:
        f = features[0]
        print(f"  Label: {f.get('label')}")
    return len(features) > 0


def test_maeasam():
    """Test MAEASaM (expected to fail - server down)."""
    print("\n" + "=" * 50)
    print("Testing MAEASaM (may be unavailable)")
    print("=" * 50)

    import httpx
    try:
        r = httpx.get("https://database.maeasam.org/", timeout=10)
        print(f"Status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Server unavailable: {type(e).__name__}")
        return None  # Not a failure, just unavailable


if __name__ == "__main__":
    results = {}

    results["Open Context"] = test_open_context()
    results["Wikidata"] = test_wikidata()
    results["Arachne"] = test_arachne()
    results["Scotland"] = test_scotland()
    results["EAMENA"] = test_eamena()
    results["P3k14c"] = test_p3k14c()
    results["MAEASaM"] = test_maeasam()

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, ok in results.items():
        if ok is None:
            status = "UNAVAILABLE (server down)"
        elif ok:
            status = "OK"
        else:
            status = "FAIL"
        print(f"  {name}: {status}")

    # Count working vs failed (exclude unavailable)
    working = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    unavailable = sum(1 for v in results.values() if v is None)

    print(f"\nWorking: {working}, Failed: {failed}, Unavailable: {unavailable}")
