# HOPE42 | UP42 Catalog Matcher

HOPE42 is a sleek, space-grade dark-themed web application that integrates with the **UP42 Catalog API** to check if your vector boundaries (AOIs) intersect with available satellite data collections.

It allows you to draw or import your vector files, select from 73 data collections classified across **Optical**, **SAR**, and **Elevation** categories, and view overlapping scene footprints on an interactive map.

---

## 🌟 Key Features

- **Multi-Format Vector Parsing**: Directly upload or paste **GeoJSON**, **KML**, **WKT**, and **Zipped Shapefiles** to display them on the map.
- **UP42 API Authentication**: Safe, token-based authentication directly with the UP42 console identity provider. Shows a connection status indicator and features a quick logout button.
- **Dynamic Collections Classification**: Auto-fetches all 73 available collections, grouping them into searchable categories (**Optical**, **SAR**, **Elevation**) with counter badges.
- **Interactive Map**: View vector boundaries and matching satellite scene footprints. Hover to highlight footprints and click to view full metadata popups.
- **Data Export**: Export matched catalog scene listings directly as **GeoJSON** feature collections or structured **CSV reports**.
- **Responsive Layout**: Designed with a glassmorphism style that automatically adjusts checkbox list heights when panels collapse.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.13+, FastAPI, Uvicorn, Requests, PyShp (`shapefile`).
- **Frontend**: Vanilla HTML5, CSS3, ES6 JavaScript, Leaflet.js (Map & Drawing tools), FontAwesome.

---

## 🚀 Quick Start

### 1. Prerequisites
Make sure you have Python 3.10+ installed on your computer.

### 2. Clone the Repository
```bash
git clone https://github.com/<your-github-username>/hope42-up42-catalog-matcher.git
cd hope42-up42-catalog-matcher
```

### 3. Set Up Virtual Environment
On Windows:
```powershell
python -m venv venv
.\venv\Scripts\activate
```
On macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the Application
Start the FastAPI server:
```bash
python -m uvicorn backend.app:app --reload --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 📂 Project Structure

```
├── backend/
│   ├── app.py              # FastAPI endpoints and static routing
│   ├── up42_client.py      # UP42 Catalog API OAuth2 and search client
│   └── vector_parser.py    # Parsers for KML, Shapefiles, WKT, GeoJSON
├── frontend/
│   ├── index.html          # Main UI structure
│   ├── style.css           # Space dark styling rules
│   └── app.js              # Leaflet map config, uploads, and search requests
├── requirements.txt        # Backend dependencies
├── test_backend.py         # Unit tests for vector parsers
└── README.md               # Project documentation
```

---

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
