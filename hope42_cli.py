#!/usr/bin/env python
"""
HOPE42 | Standalone UP42 Catalog Search CLI Tool

This self-contained script allows you to query the UP42 Catalog API for satellite imagery 
overlapping a vector boundary file (GeoJSON, KML, Zipped Shapefile, or WKT), and outputs the 
available datasets into a text report grouped by Optical, SAR, and Elevation.
"""

import os
import re
import sys
import json
import time
import getpass
import argparse
import urllib.request
import urllib.error
import zipfile
import io
from datetime import datetime

# Optional: Try importing shapefile (pyshp)
try:
    import shapefile
    SHAPEFILE_SUPPORT = True
except ImportError:
    SHAPEFILE_SUPPORT = False

# ==========================================
# 1. VECTOR PARSERS (Zero-dependency & pyshp)
# ==========================================

def parse_wkt(wkt_str):
    wkt_str = wkt_str.strip().upper()
    
    # POINT
    point_match = re.match(r'^POINT\s*\(\s*(.*?)\s*\)$', wkt_str)
    if point_match:
        coords_str = point_match.group(1)
        parts = coords_str.strip().split()
        if len(parts) >= 2:
            return {"type": "Point", "coordinates": [float(parts[0]), float(parts[1])]}
            
    # LINESTRING
    linestring_match = re.match(r'^LINESTRING\s*\(\s*(.*?)\s*\)$', wkt_str)
    if linestring_match:
        coords_str = linestring_match.group(1)
        coordinates = []
        for pts in coords_str.split(','):
            parts = pts.strip().split()
            if len(parts) >= 2:
                coordinates.append([float(parts[0]), float(parts[1])])
        return {"type": "LineString", "coordinates": coordinates}
        
    # POLYGON
    polygon_match = re.match(r'^POLYGON\s*\(\s*\((.*?)\)\s*\)$', wkt_str)
    if polygon_match:
        coords_str = polygon_match.group(1)
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
        return {"type": "Polygon", "coordinates": coordinates}
        
    # MULTIPOLYGON
    multipolygon_match = re.match(r'^MULTIPOLYGON\s*\(\s*(.*?)\s*\)$', wkt_str)
    if multipolygon_match:
        content = multipolygon_match.group(1)
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
        return {"type": "MultiPolygon", "coordinates": polygons}
        
    raise ValueError(f"Unsupported or invalid WKT format.")

def parse_kml_coordinates(coords_str):
    coords = []
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

def parse_kml(kml_bytes):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(kml_bytes)
    
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
            
    features = []
    for placemark in root.iter('Placemark'):
        name_node = placemark.find('name')
        name = name_node.text if name_node is not None else "Unnamed"
        
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
                    "properties": {"name": name},
                    "geometry": {"type": "Polygon", "coordinates": coordinates}
                })
                continue
                
        linestring = placemark.find('.//LineString')
        if linestring is not None:
            coords_node = linestring.find('.//coordinates')
            if coords_node is not None and coords_node.text:
                coords = parse_kml_coordinates(coords_node.text)
                if coords:
                    features.append({
                        "type": "Feature",
                        "properties": {"name": name},
                        "geometry": {"type": "LineString", "coordinates": coords}
                    })
                    continue
                    
        point = placemark.find('.//Point')
        if point is not None:
            coords_node = point.find('.//coordinates')
            if coords_node is not None and coords_node.text:
                coords = parse_kml_coordinates(coords_node.text)
                if coords:
                    features.append({
                        "type": "Feature",
                        "properties": {"name": name},
                        "geometry": {"type": "Point", "coordinates": coords[0]}
                    })
                    continue
    return {"type": "FeatureCollection", "features": features}

def parse_zip_shapefile(zip_bytes):
    if not SHAPEFILE_SUPPORT:
        raise ImportError("pyshp library is required to parse shapefiles. Run: pip install pyshp")
        
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    filenames = z.namelist()
    
    base_name = None
    for name in filenames:
        if name.endswith('.shp'):
            base_name = name[:-4]
            break
            
    if not base_name:
        raise ValueError("No .shp file found in ZIP archive.")
        
    shp_data = io.BytesIO(z.read(base_name + '.shp'))
    shx_data = io.BytesIO(z.read(base_name + '.shx')) if (base_name + '.shx') in filenames else None
    dbf_data = io.BytesIO(z.read(base_name + '.dbf')) if (base_name + '.dbf') in filenames else None
    
    reader = shapefile.Reader(shp=shp_data, shx=shx_data, dbf=dbf_data)
    features = []
    
    for shape_record in reader.shapeRecords():
        geometry = shape_record.shape.__geo_interface__
        properties = {}
        if dbf_data:
            record = shape_record.record
            field_names = [f[0] for f in reader.fields[1:]]
            for field_name, val in zip(field_names, record):
                if isinstance(val, bytes):
                    val = val.decode('utf-8', errors='ignore')
                properties[field_name] = val
        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry
        })
    return {"type": "FeatureCollection", "features": features}

def load_vector_file(filepath):
    """
    Reads a vector file from path and extracts its geometry.
    Returns a GeoJSON geometry dictionary.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Vector file not found at: {filepath}")
        
    filename = os.path.basename(filepath)
    ext = filename.lower().split('.')[-1]
    
    with open(filepath, 'rb') as f:
        file_bytes = f.read()
        
    if ext in ['geojson', 'json']:
        data = json.loads(file_bytes.decode('utf-8', errors='ignore'))
        if "type" in data:
            if data["type"] == "FeatureCollection" and data.get("features"):
                return data["features"][0]["geometry"]
            elif data["type"] == "Feature":
                return data["geometry"]
            elif data["type"] in ["Polygon", "MultiPolygon", "Point", "LineString"]:
                return data
        raise ValueError("Invalid GeoJSON format.")
        
    elif ext == 'kml':
        fc = parse_kml(file_bytes)
        if fc.get("features"):
            return fc["features"][0]["geometry"]
        raise ValueError("KML file contains no valid geometries.")
        
    elif ext in ['wkt', 'txt']:
        wkt_str = file_bytes.decode('utf-8', errors='ignore').strip()
        return parse_wkt(wkt_str)
        
    elif ext == 'zip':
        fc = parse_zip_shapefile(file_bytes)
        if fc.get("features"):
            return fc["features"][0]["geometry"]
        raise ValueError("Shapefile ZIP contains no valid geometries.")
        
    else:
        raise ValueError(f"Unsupported file format: .{ext}")

# ==========================================
# 2. UP42 HTTP CLIENT
# ==========================================

class UP42Client:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.token = None
        self.expiry = 0
        self.auth_url = "https://auth.up42.com/realms/public/protocol/openid-connect/token"
        self.api_url = "https://api.up42.com"

    def get_token(self):
        if self.token and time.time() < self.expiry - 10:
            return self.token
            
        data = f"username={urllib.parse.quote(self.email)}&password={urllib.parse.quote(self.password)}&grant_type=password&client_id=up42-api"
        req = urllib.request.Request(
            self.auth_url,
            data=data.encode('utf-8'),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                res_data = json.loads(res.read().decode('utf-8'))
                self.token = res_data["access_token"]
                self.expiry = time.time() + res_data.get("expires_in", 300)
                return self.token
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            raise Exception(f"UP42 Login Failed (HTTP {e.code}): {err_msg}")
        except Exception as e:
            raise Exception(f"Network error during login: {e}")

    def fetch_collections(self):
        url = f"{self.api_url}/v2/collections?size=250"
        headers = {"accept": "application/json"}
        # Add auth if available
        try:
            token = self.get_token()
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
            
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode('utf-8'))
            return data.get("content", [])

    def search_catalog(self, host_name, collections, geometry, datetime_str, cloud_cover=None):
        token = self.get_token()
        url = f"{self.api_url}/catalog/hosts/{host_name}/stac/search"
        
        body = {
            "collections": collections,
            "intersects": geometry,
            "limit": 500
        }
        if datetime_str:
            body["datetime"] = datetime_str
        if cloud_cover is not None:
            body["query"] = {
                "eo:cloud_cover": {
                    "lte": cloud_cover
                }
            }
            
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "accept": "application/json"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                return json.loads(res.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            # 404 means search not available for this host
            if e.code == 404:
                return {"type": "FeatureCollection", "features": []}
            err_msg = e.read().decode('utf-8')
            print(f"[Warning] Search failed for host {host_name}: HTTP {e.code} - {err_msg}")
            return {"type": "FeatureCollection", "features": []}
        except Exception as e:
            print(f"[Warning] Search error for host {host_name}: {e}")
            return {"type": "FeatureCollection", "features": []}

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def load_dot_env():
    """
    Simple function to read credentials from .env file if it exists.
    """
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

# ==========================================
# 4. MAIN PROGRAM FLOW
# ==========================================

def main():
    print("=" * 60)
    print(" HOPE42 | UP42 Catalog Search CLI Tool")
    print("=" * 60)
    
    # Argument parser
    parser = argparse.ArgumentParser(description="Standalone CLI to query UP42 Catalog and save results to txt file.")
    parser.add_argument("-f", "--file", help="Path to vector boundary file (GeoJSON, KML, ZIP, WKT/TXT)")
    parser.add_argument("-s", "--start", help="Start Date (YYYY-MM-DD)")
    parser.add_argument("-e", "--end", help="End Date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("-c", "--cloud", type=int, default=20, help="Max cloud cover percentage (0-100). Default is 20%%.")
    parser.add_argument("-o", "--output", default="up42_search_report.txt", help="Output text file path. Default: up42_search_report.txt")
    
    args = parser.parse_args()
    
    # 1. Load credentials
    env = load_dot_env()
    email = env.get("UP42_EMAIL") or os.environ.get("UP42_EMAIL")
    password = env.get("UP42_PASSWORD") or os.environ.get("UP42_PASSWORD")
    
    if not email:
        email = input("Enter your UP42 Console Email: ").strip()
    if not password:
        password = getpass.getpass("Enter your UP42 Console Password: ")
        
    if not email or not password:
        print("[Error] Email and Password are required to query UP42.")
        sys.exit(1)
        
    # 2. Gather Inputs
    vector_path = args.file
    if not vector_path:
        vector_path = input("Enter path to your Vector File (GeoJSON, KML, WKT TXT, ZIP Shapefile): ").strip().strip('"').strip("'")
        
    if not os.path.exists(vector_path):
        print(f"[Error] File not found: {vector_path}")
        sys.exit(1)
        
    start_date = args.start
    if not start_date:
        start_date = input("Enter Start Date (YYYY-MM-DD): ").strip()
        
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        print("[Error] Invalid start date format. Must be YYYY-MM-DD.")
        sys.exit(1)
        
    end_date = args.end
    if not end_date:
        # Prompt with today's date as default
        today_str = datetime.today().strftime('%Y-%m-%d')
        end_date = input(f"Enter End Date (YYYY-MM-DD) [Default: {today_str}]: ").strip()
        if not end_date:
            end_date = today_str
            
    try:
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        print("[Error] Invalid end date format. Must be YYYY-MM-DD.")
        sys.exit(1)

    datetime_str = f"{start_date}T00:00:00Z/{end_date}T23:59:59Z"
    
    print("\n[1/4] Parsing vector file...")
    try:
        geometry = load_vector_file(vector_path)
        print(f" -> Geometry parsed successfully (Type: {geometry['type']})")
    except Exception as e:
        print(f"[Error] Failed to parse vector boundary: {e}")
        sys.exit(1)

    # 3. Authenticate
    print("[2/4] Connecting and authenticating with UP42...")
    try:
        client = UP42Client(email, password)
        # Force token check
        client.get_token()
        print(" -> Authentication Successful!")
    except Exception as e:
        print(f"[Error] Authentication failed: {e}")
        sys.exit(1)

    # 4. Fetch collections glossary for host & category mapping
    print("[3/4] Fetching catalog collections metadata...")
    try:
        raw_collections = client.fetch_collections()
        
        # Map each collection name to its host and productType
        col_to_host = {}
        col_to_type = {}
        col_to_title = {}
        
        for item in raw_collections:
            name = item.get("name")
            title = item.get("title", name)
            
            # Check integrations for Search capability
            integrations = item.get("integrations", [])
            if "SEARCH_AVAILABLE" not in integrations:
                continue
                
            # Find host provider
            host = None
            for provider in item.get("providers", []):
                if "HOST" in provider.get("roles", []):
                    host = provider.get("name")
                    break
            if not host and item.get("providers"):
                host = item["providers"][0].get("name")
                
            if not host:
                continue
                
            # Classify product type
            product_type = item.get("metadata", {}).get("productType")
            if not product_type:
                name_lower = name.lower()
                if "dem" in name_lower or "elevation" in name_lower or "terrain" in name_lower:
                    product_type = "ELEVATION"
                elif "sar" in name_lower or "radar" in name_lower or "capella" in name_lower or "iceye" in name_lower or "umbra" in name_lower:
                    product_type = "SAR"
                else:
                    product_type = "OPTICAL"
            else:
                product_type = product_type.upper()
                
            col_to_host[name] = host
            col_to_type[name] = product_type
            col_to_title[name] = title
            
        print(f" -> Found {len(col_to_host)} searchable catalog collections.")
    except Exception as e:
        print(f"[Error] Failed to fetch collections mapping: {e}")
        sys.exit(1)

    # 5. Group collections by Host
    host_groups = {}
    for col_name, host in col_to_host.items():
        if host not in host_groups:
            host_groups[host] = []
        host_groups[host].append(col_name)

    # 6. Execute Search Query per Host
    print("[4/4] Searching UP42 Catalog across all hosts...")
    
    optical_results = []
    sar_results = []
    elevation_results = []
    
    for host, cols in host_groups.items():
        print(f" -> Querying host '{host}' for collections: {len(cols)}")
        results = client.search_catalog(
            host_name=host,
            collections=cols,
            geometry=geometry,
            datetime_str=datetime_str,
            cloud_cover=args.cloud
        )
        
        features = results.get("features", [])
        for feature in features:
            props = feature.get("properties") or {}
            col_name = feature.get("collection") or props.get("collection")
            if not col_name:
                continue
                
            title = col_to_title.get(col_name, col_name)
            p_type = col_to_type.get(col_name, "OPTICAL")
            
            # Extract common properties
            date_str = props.get("datetime") or props.get("acquisition_date") or "N/A"
            if date_str != "N/A":
                # Make date human readable
                try:
                    date_str = date_str.split("T")[0]
                except Exception:
                    pass
                    
            cloud = props.get("eo:cloud_cover") or props.get("cloud_cover")
            gsd = props.get("resolution") or props.get("gsd") or "N/A"
            scene_id = feature.get("id") or "N/A"
            
            scene_item = {
                "collection": title,
                "date": date_str,
                "cloud": f"{cloud:.1f}%" if cloud is not None else "N/A",
                "gsd": f"{gsd} m" if isinstance(gsd, (int, float)) else gsd,
                "id": scene_id,
                "host": host
            }
            
            if p_type == "OPTICAL":
                optical_results.append(scene_item)
            elif p_type == "SAR":
                sar_results.append(scene_item)
            elif p_type == "ELEVATION":
                elevation_results.append(scene_item)

    # 7. Write Notepad Report (.txt file)
    output_path = args.output
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("             HOPE42 | UP42 CATALOG SEARCH REPORT\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Vector File:  {os.path.basename(vector_path)} (Type: {geometry['type']})\n")
            f.write(f"Date Range:   {start_date} to {end_date}\n")
            f.write(f"Max Cloud:    {args.cloud}%\n\n")
            
            f.write("SUMMARY STATS:\n")
            f.write("-" * 25 + "\n")
            f.write(f" -> Optical Scenes:   {len(optical_results)}\n")
            f.write(f" -> SAR Scenes:       {len(sar_results)}\n")
            f.write(f" -> Elevation Scenes: {len(elevation_results)}\n")
            f.write(f" -> Total Found:      {len(optical_results) + len(sar_results) + len(elevation_results)}\n\n")
            
            # --- OPTICAL ---
            f.write("=" * 70 + "\n")
            f.write(" 1. OPTICAL DATASETS\n")
            f.write("=" * 70 + "\n")
            if not optical_results:
                f.write("No matching optical scenes found.\n\n")
            else:
                f.write(f"{'SATELLITE/COLLECTION':<28} | {'DATE':<10} | {'CLOUD':<6} | {'RESOLUTION':<10} | {'SCENE ID'}\n")
                f.write("-" * 70 + "\n")
                for item in sorted(optical_results, key=lambda x: x["date"], reverse=True):
                    f.write(f"{item['collection'][:28]:<28} | {item['date']:<10} | {item['cloud']:<6} | {item['gsd']:<10} | {item['id']}\n")
                f.write("\n")
                
            # --- SAR ---
            f.write("=" * 70 + "\n")
            f.write(" 2. SAR (RADAR) DATASETS\n")
            f.write("=" * 70 + "\n")
            if not sar_results:
                f.write("No matching SAR scenes found.\n\n")
            else:
                f.write(f"{'RADAR/COLLECTION':<28} | {'DATE':<10} | {'RESOLUTION':<10} | {'SCENE ID'}\n")
                f.write("-" * 70 + "\n")
                for item in sorted(sar_results, key=lambda x: x["date"], reverse=True):
                    f.write(f"{item['collection'][:28]:<28} | {item['date']:<10} | {item['gsd']:<10} | {item['id']}\n")
                f.write("\n")
                
            # --- ELEVATION ---
            f.write("=" * 70 + "\n")
            f.write(" 3. ELEVATION (DEM) DATASETS\n")
            f.write("=" * 70 + "\n")
            if not elevation_results:
                f.write("No matching elevation datasets found.\n\n")
            else:
                f.write(f"{'DEM/COLLECTION':<28} | {'DATE':<10} | {'RESOLUTION':<10} | {'SCENE ID'}\n")
                f.write("-" * 70 + "\n")
                for item in sorted(elevation_results, key=lambda x: x["date"], reverse=True):
                    f.write(f"{item['collection'][:28]:<28} | {item['date']:<10} | {item['gsd']:<10} | {item['id']}\n")
                f.write("\n")
                
            f.write("-" * 70 + "\n")
            f.write("End of Report\n")
            
        print("\n" + "=" * 60)
        print(f" SUCCESS: Results saved to report file!")
        print(f" Output Path: {os.path.abspath(output_path)}")
        print("=" * 60)
        
        # Open in Notepad on Windows automatically if possible
        if sys.platform == 'win32':
            os.system(f'notepad.exe "{output_path}"')
            
    except Exception as e:
        print(f"[Error] Failed to write report file: {e}")

if __name__ == "__main__":
    main()
