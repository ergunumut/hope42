import unittest
import json
from backend.vector_parser import parse_wkt, parse_kml, parse_vector_data

class TestVectorParser(unittest.TestCase):
    def test_parse_wkt_point(self):
        wkt = "POINT (35.5 39.2)"
        geojson = parse_wkt(wkt)
        self.assertEqual(geojson["type"], "Point")
        self.assertEqual(geojson["coordinates"], [35.5, 39.2])

    def test_parse_wkt_polygon(self):
        wkt = "POLYGON ((35.0 39.0, 36.0 39.0, 36.0 40.0, 35.0 40.0, 35.0 39.0))"
        geojson = parse_wkt(wkt)
        self.assertEqual(geojson["type"], "Polygon")
        self.assertEqual(len(geojson["coordinates"]), 1)
        self.assertEqual(len(geojson["coordinates"][0]), 5)
        self.assertEqual(geojson["coordinates"][0][0], [35.0, 39.0])

    def test_parse_wkt_multipolygon(self):
        wkt = "MULTIPOLYGON (((30 20, 45 40, 10 40, 30 20)), ((15 5, 40 10, 10 20, 15 5)))"
        geojson = parse_wkt(wkt)
        self.assertEqual(geojson["type"], "MultiPolygon")
        self.assertEqual(len(geojson["coordinates"]), 2)

    def test_parse_kml(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              35.0,39.0,0.0 36.0,39.0,0.0 36.0,40.0,0.0 35.0,40.0,0.0 35.0,39.0,0.0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
        geojson = parse_kml(kml_content.encode('utf-8'))
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 1)
        feature = geojson["features"][0]
        self.assertEqual(feature["properties"]["name"], "Test Polygon")
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        self.assertEqual(feature["geometry"]["coordinates"][0][0], [35.0, 39.0])

    def test_parse_vector_geojson(self):
        geojson_str = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Point",
                    "coordinates": [35.0, 39.0]
                }
            }]
        })
        parsed = parse_vector_data(geojson_str.encode('utf-8'), "test.geojson")
        self.assertEqual(parsed["type"], "FeatureCollection")
        self.assertEqual(len(parsed["features"]), 1)

if __name__ == "__main__":
    unittest.main()
