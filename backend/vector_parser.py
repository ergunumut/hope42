import re
import json
import xml.etree.ElementTree as ET
import zipfile
import io
import shapefile

def parse_wkt(wkt_str: str) -> dict:
    """
    Parses a WKT (Well-Known Text) string and converts it to a GeoJSON geometry dictionary.
    Supports POINT, LINESTRING, POLYGON, and MULTIPOLYGON.
    """
    wkt_str = wkt_str.strip().upper()
    
    # 1. Match POINT
    point_match = re.match(r'^POINT\s*\(\s*(.*?)\s*\)$', wkt_str)
    if point_match:
        coords_str = point_match.group(1)
        parts = coords_str.strip().split()
        if len(parts) >= 2:
            return {
                "type": "Point",
                "coordinates": [float(parts[0]), float(parts[1])]
            }
            
    # 2. Match LINESTRING
    linestring_match = re.match(r'^LINESTRING\s*\(\s*(.*?)\s*\)$', wkt_str)
    if linestring_match:
        coords_str = linestring_match.group(1)
        coordinates = []
        for pts in coords_str.split(','):
            parts = pts.strip().split()
            if len(parts) >= 2:
                coordinates.append([float(parts[0]), float(parts[1])])
        return {
            "type": "LineString",
            "coordinates": coordinates
        }
        
    # 3. Match POLYGON
    polygon_match = re.match(r'^POLYGON\s*\(\s*\((.*?)\)\s*\)$', wkt_str)
    if polygon_match:
        coords_str = polygon_match.group(1)
        # Handle inner rings: POLYGON ((x y, x y), (x y, x y))
        rings = re.split(r'\)\s*,\s*\(', coords_str)
        coordinates = []
        for ring in rings:
            ring = ring.replace('(', '').replace(')', '')
            ring_coords = []
            for pts in ring.split(','):
                pts = pts.strip()
                if not pts:
                    continue
                parts = pts.split()
                if len(parts) >= 2:
                    ring_coords.append([float(parts[0]), float(parts[1])])
            if ring_coords:
                coordinates.append(ring_coords)
        return {
            "type": "Polygon",
            "coordinates": coordinates
        }
        
    # 4. Match MULTIPOLYGON
    multipolygon_match = re.match(r'^MULTIPOLYGON\s*\(\s*(.*?)\s*\)$', wkt_str)
    if multipolygon_match:
        content = multipolygon_match.group(1)
        # MULTIPOLYGON (((30 20, 45 40, 10 40, 30 20)), ((15 5, 40 10, 10 20, 15 5)))
        # Split by outer boundaries of polygons which are separated by )), ((
        # We can clean up brackets and extract rings recursively
        # A simpler way is to find each POLYGON inside, e.g. matching ((...))
        poly_matches = re.findall(r'\(\s*\((.*?)\)\s*\)', content)
        polygons = []
        for poly_str in poly_matches:
            rings = re.split(r'\)\s*,\s*\(', poly_str)
            poly_coords = []
            for ring in rings:
                ring_coords = []
                for pts in ring.split(','):
                    pts = pts.strip()
                    if not pts:
                        continue
                    parts = pts.split()
                    if len(parts) >= 2:
                        ring_coords.append([float(parts[0]), float(parts[1])])
                if ring_coords:
                    poly_coords.append(ring_coords)
            if poly_coords:
                polygons.append(poly_coords)
        return {
            "type": "MultiPolygon",
            "coordinates": polygons
        }
        
    raise ValueError(f"Unsupported or invalid WKT format: {wkt_str[:50]}...")

def parse_kml_coordinates(coords_str: str) -> list:
    coords = []
    # KML coordinates are space-separated or newline-separated points: "lon,lat,alt lon,lat,alt ..."
    # Some KML files use commas and spaces in varying formats
    for pt in coords_str.strip().split():
        pt = pt.strip()
        if not pt:
            continue
        parts = pt.split(',')
        if len(parts) >= 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except ValueError:
                pass
    return coords

def parse_kml(kml_bytes: bytes) -> dict:
    """
    Parses a KML byte string and extracts all geometries into a GeoJSON FeatureCollection.
    """
    root = ET.fromstring(kml_bytes)
    
    # Remove XML namespaces to simplify element tags
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
            
    features = []
    
    for placemark in root.iter('Placemark'):
        name_node = placemark.find('name')
        name = name_node.text if name_node is not None else "Unnamed Placemark"
        
        # Check Polygon
        polygon = placemark.find('.//Polygon')
        if polygon is not None:
            coordinates = []
            outer = polygon.find('.//outerBoundaryIs//coordinates')
            if outer is not None and outer.text:
                outer_coords = parse_kml_coordinates(outer.text)
                if outer_coords:
                    coordinates.append(outer_coords)
            
            for inner in polygon.findall('.//innerBoundaryIs//coordinates'):
                if inner.text:
                    inner_coords = parse_kml_coordinates(inner.text)
                    if inner_coords:
                        coordinates.append(inner_coords)
            
            if coordinates:
                features.append({
                    "type": "Feature",
                    "properties": {"name": name, "type": "Polygon"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": coordinates
                    }
                })
                continue
                
        # Check LineString
        linestring = placemark.find('.//LineString')
        if linestring is not None:
            coords_node = linestring.find('.//coordinates')
            if coords_node is not None and coords_node.text:
                coords = parse_kml_coordinates(coords_node.text)
                if coords:
                    features.append({
                        "type": "Feature",
                        "properties": {"name": name, "type": "LineString"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords
                        }
                    })
                    continue
                    
        # Check Point
        point = placemark.find('.//Point')
        if point is not None:
            coords_node = point.find('.//coordinates')
            if coords_node is not None and coords_node.text:
                coords = parse_kml_coordinates(coords_node.text)
                if coords:
                    features.append({
                        "type": "Feature",
                        "properties": {"name": name, "type": "Point"},
                        "geometry": {
                            "type": "Point",
                            "coordinates": coords[0]
                        }
                    })
                    continue

    return {
        "type": "FeatureCollection",
        "features": features
    }

def parse_zip_shapefile(zip_bytes: bytes) -> dict:
    """
    Parses a zipped shapefile (containing .shp, .shx, .dbf) and returns a GeoJSON FeatureCollection.
    """
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    filenames = z.namelist()
    
    base_name = None
    for name in filenames:
        if name.endswith('.shp'):
            base_name = name[:-4]
            break
            
    if not base_name:
        raise ValueError("No .shp file found in the ZIP archive.")
        
    shp_data = io.BytesIO(z.read(base_name + '.shp'))
    shx_data = io.BytesIO(z.read(base_name + '.shx')) if (base_name + '.shx') in filenames else None
    dbf_data = io.BytesIO(z.read(base_name + '.dbf')) if (base_name + '.dbf') in filenames else None
    
    # Open shapefile reader
    reader = shapefile.Reader(shp=shp_data, shx=shx_data, dbf=dbf_data)
    
    features = []
    for shape_record in reader.shapeRecords():
        geometry = shape_record.shape.__geo_interface__
        properties = {}
        
        if dbf_data:
            record = shape_record.record
            # reader.fields has names, skip first field ('DeletionFlag')
            field_names = [f[0] for f in reader.fields[1:]]
            for field_name, val in zip(field_names, record):
                if isinstance(val, bytes):
                    try:
                        val = val.decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                properties[field_name] = val
                
        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry
        })
        
    return {
        "type": "FeatureCollection",
        "features": features
    }

def parse_vector_data(file_bytes: bytes, filename: str) -> dict:
    """
    Detects file type by extension and parses it into a GeoJSON FeatureCollection format.
    """
    ext = filename.lower().split('.')[-1]
    
    if ext == 'geojson' or ext == 'json':
        data = json.loads(file_bytes.decode('utf-8', errors='ignore'))
        # If it's a raw geometry, wrap it in a feature
        if "type" in data:
            if data["type"] in ["Point", "LineString", "Polygon", "MultiPolygon", "MultiPoint", "MultiLineString"]:
                return {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "properties": {"name": filename},
                        "geometry": data
                    }]
                }
            elif data["type"] == "Feature":
                return {
                    "type": "FeatureCollection",
                    "features": [data]
                }
            elif data["type"] == "FeatureCollection":
                return data
        raise ValueError("Invalid GeoJSON format")
        
    elif ext == 'kml':
        return parse_kml(file_bytes)
        
    elif ext == 'wkt' or ext == 'txt':
        wkt_str = file_bytes.decode('utf-8', errors='ignore').strip()
        geometry = parse_wkt(wkt_str)
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"name": filename, "type": geometry["type"]},
                "geometry": geometry
            }]
        }
        
    elif ext == 'zip':
        return parse_zip_shapefile(file_bytes)
        
    else:
        raise ValueError(f"Unsupported file format: {ext}")
