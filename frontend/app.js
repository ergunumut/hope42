// COSMOS | UP42 Catalog Matcher Logic

// Application State
const state = {
    email: localStorage.getItem('cosmos_email') || '',
    password: '',
    isConnected: false,
    collections: [],
    selectedCollections: new Set(), // Track selected collection names
    boundaries: [], // Keep track of layers in drawnItems
    searchResults: null,
    sceneLayers: {} // Maps feature ID to L.GeoJSON layer
};

// Elements
const authDetailsCard = document.getElementById('authDetailsCard');
const authCheckmark = document.getElementById('authCheckmark');
const authSuccessContainer = document.getElementById('authSuccessContainer');
const connectedUserEmail = document.getElementById('connectedUserEmail');
const btnLogout = document.getElementById('btnLogout');

const authForm = document.getElementById('authForm');
const authEmail = document.getElementById('authEmail');
const authPassword = document.getElementById('authPassword');
const btnConnect = document.getElementById('btnConnect');
const authStatusBadge = document.getElementById('authStatusBadge');

const tabBtns = document.querySelectorAll('.tab-btn');
const tabPanes = document.querySelectorAll('.tab-pane');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const wktInput = document.getElementById('wktInput');
const btnLoadWkt = document.getElementById('btnLoadWkt');
const btnDrawPolygon = document.getElementById('btnDrawPolygon');
const btnDrawBbox = document.getElementById('btnDrawBbox');

const activeBoundariesList = document.getElementById('activeBoundariesList');
const boundaryCountSpan = document.getElementById('boundaryCount');
const btnClearBoundaries = document.getElementById('btnClearBoundaries');

const startDateInput = document.getElementById('startDate');
const endDateInput = document.getElementById('endDate');
const cloudCoverSlider = document.getElementById('cloudCover');
const cloudCoverValSpan = document.getElementById('cloudCoverVal');
const searchLimitSelect = document.getElementById('searchLimit');
const collectionsListDiv = document.getElementById('collectionsList');

// Sub-tabs & select actions elements
const countOPTICAL = document.getElementById('countOPTICAL');
const countSAR = document.getElementById('countSAR');
const countELEVATION = document.getElementById('countELEVATION');
const btnSelectAllCol = document.getElementById('btnSelectAllCol');
const btnDeselectAllCol = document.getElementById('btnDeselectAllCol');
let activeColTab = 'OPTICAL';

const btnSearch = document.getElementById('btnSearch');

const searchProgressOverlay = document.getElementById('searchProgressOverlay');
const searchProgressText = document.getElementById('searchProgressText');

const resultsPanel = document.getElementById('resultsPanel');
const btnCloseResults = document.getElementById('btnCloseResults');
const resultsCountSpan = document.getElementById('resultsCount');
const resultsListDiv = document.getElementById('resultsList');
const resultFilterSearch = document.getElementById('resultFilterSearch');
const btnExportGeoJson = document.getElementById('btnExportGeoJson');
const btnExportCsv = document.getElementById('btnExportCsv');

const metadataModal = document.getElementById('metadataModal');
const metadataModalBody = document.getElementById('metadataModalBody');
const btnMetadataModalClose = document.getElementById('btnMetadataModalClose');

// Initialize Map
const map = L.map('map', {
    zoomControl: false
}).setView([39.0, 35.0], 5); // Default view over Anatolia / Mid-East

// Add Zoom control at top-right
L.control.zoom({ position: 'topright' }).addTo(map);

// Add Dark Base Layer
const baseLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

// Feature Groups for Map Overlays
const drawnItems = new L.FeatureGroup().addTo(map);
const sceneFootprints = new L.FeatureGroup().addTo(map);

// Add Drawing Controls
const drawOptions = {
    edit: {
        featureGroup: drawnItems,
        remove: true
    },
    draw: {
        polyline: false,
        circle: false,
        circlemarker: false,
        marker: false,
        polygon: {
            allowIntersection: false,
            shapeOptions: {
                color: '#00f2fe',
                fillColor: 'rgba(0, 242, 254, 0.1)',
                weight: 2
            }
        },
        rectangle: {
            shapeOptions: {
                color: '#00f2fe',
                fillColor: 'rgba(0, 242, 254, 0.1)',
                weight: 2
            }
        }
    }
};

const drawControl = new L.Control.Draw(drawOptions);
map.addControl(drawControl);

// Populate default search parameters (Last 3 months to today)
const today = new Date();
const threeMonthsAgo = new Date();
threeMonthsAgo.setMonth(today.getMonth() - 3);

startDateInput.value = threeMonthsAgo.toISOString().split('T')[0];
endDateInput.value = today.toISOString().split('T')[0];

if (state.email) {
    authEmail.value = state.email;
}

// Map Event Handlers
map.on(L.Draw.Event.CREATED, function (e) {
    const layer = e.layer;
    layer.options.color = '#00f2fe';
    layer.options.fillColor = 'rgba(0, 242, 254, 0.1)';
    layer.options.weight = 2;
    drawnItems.addLayer(layer);
    updateBoundariesList();
});

map.on(L.Draw.Event.DELETED, function (e) {
    updateBoundariesList();
});

map.on(L.Draw.Event.EDITED, function (e) {
    updateBoundariesList();
});

// Programmatic Drawing Trigger
btnDrawPolygon.addEventListener('click', () => {
    new L.Draw.Polygon(map, drawOptions.draw.polygon).enable();
});

btnDrawBbox.addEventListener('click', () => {
    new L.Draw.Rectangle(map, drawOptions.draw.rectangle).enable();
});

// Boundary State Management
function updateBoundariesList() {
    activeBoundariesList.innerHTML = '';
    state.boundaries = [];
    
    const layers = drawnItems.getLayers();
    boundaryCountSpan.innerText = layers.length;

    if (layers.length === 0) {
        activeBoundariesList.innerHTML = '<p class="empty-list-text">No boundaries added. Add one above to start searching.</p>';
        btnClearBoundaries.style.display = 'none';
        validateSearchReady();
        return;
    }

    btnClearBoundaries.style.display = 'block';

    layers.forEach((layer, idx) => {
        const id = L.stamp(layer);
        let type = 'Polygon';
        if (layer instanceof L.Rectangle) {
            type = 'Rectangle';
        }
        
        const name = `Boundary #${idx + 1}`;
        state.boundaries.push({ id, layer, name, type });

        const item = document.createElement('div');
        item.className = 'boundary-item';
        item.innerHTML = `
            <div class="boundary-item-info">
                <i class="fa-solid fa-square-poll-horizontal icon-glow"></i>
                <span class="boundary-item-name">${name}</span>
                <span class="boundary-item-type">${type}</span>
            </div>
            <button class="btn-remove-boundary" data-id="${id}">
                <i class="fa-solid fa-xmark"></i>
            </button>
        `;
        
        // Remove individual boundary
        item.querySelector('.btn-remove-boundary').addEventListener('click', (e) => {
            const layerId = e.currentTarget.getAttribute('data-id');
            drawnItems.removeLayer(layers.find(l => L.stamp(l) == layerId));
            updateBoundariesList();
        });

        // Zoom/Pan to boundary on click
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.btn-remove-boundary')) {
                map.fitBounds(layer.getBounds(), { padding: [20, 20] });
            }
        });

        activeBoundariesList.appendChild(item);
    });

    validateSearchReady();
}

btnClearBoundaries.addEventListener('click', () => {
    drawnItems.clearLayers();
    updateBoundariesList();
});

// Authentication Setup
authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    btnConnect.disabled = true;
    btnConnect.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';
    
    const email = authEmail.value.strip ? authEmail.value.strip() : authEmail.value;
    const password = authPassword.value;

    try {
        const response = await fetch('/api/auth/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            state.email = email;
            state.password = password;
            state.isConnected = true;
            localStorage.setItem('cosmos_email', email);

            // Update badge UI
            authStatusBadge.innerHTML = `
                <span class="status-dot online"></span>
                <span class="status-text">Connected</span>
            `;
            
            // Connected UI transitions
            authCheckmark.style.display = 'inline-block';
            authForm.style.display = 'none';
            connectedUserEmail.innerText = email;
            authSuccessContainer.style.display = 'flex';
            
            // Collapse details card
            authDetailsCard.removeAttribute('open');
            
            showNotification('Success', 'Connected to UP42 console.', 'success');
            
            // Reload collections with auth headers
            fetchCollections();
        } else {
            throw new Error(result.detail || 'Authentication failed');
        }
    } catch (err) {
        state.isConnected = false;
        authStatusBadge.innerHTML = `
            <span class="status-dot offline"></span>
            <span class="status-text">Auth Failed</span>
        `;
        showNotification('Error', err.message, 'error');
    } finally {
        btnConnect.disabled = false;
        btnConnect.innerHTML = '<i class="fa-solid fa-plug"></i> Connect Console';
        validateSearchReady();
    }
});

// Logout Action
btnLogout.addEventListener('click', () => {
    state.email = '';
    state.password = '';
    state.isConnected = false;
    localStorage.removeItem('cosmos_email');
    
    // Reset Auth UI state
    authStatusBadge.innerHTML = `
        <span class="status-dot offline"></span>
        <span class="status-text">Disconnected</span>
    `;
    authCheckmark.style.display = 'none';
    authSuccessContainer.style.display = 'none';
    authForm.style.display = 'flex';
    authEmail.value = '';
    authPassword.value = '';
    
    // Automatically open the card for reconnecting
    authDetailsCard.setAttribute('open', '');
    
    showNotification('Disconnected', 'Logged out from UP42 console.', 'info');
    
    // Reset selections and reload collections publicly
    state.selectedCollections.clear();
    fetchCollections();
    validateSearchReady();
});

// Tab Switching
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));
        
        btn.classList.add('active');
        const tabId = btn.getAttribute('data-tab');
        document.getElementById(tabId).classList.add('active');
    });
});

// Drag/Drop Upload File Handlers
dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleUploadedFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleUploadedFile(fileInput.files[0]);
    }
});

async function handleUploadedFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    showNotification('Uploading', `Processing ${file.name}...`, 'info');

    try {
        const response = await fetch('/api/parse-vector', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'File parsing error');
        }

        const geojson = await response.json();
        addGeoJsonToDrawnItems(geojson, file.name);
        showNotification('Success', `Loaded boundary from ${file.name}`, 'success');
    } catch (err) {
        showNotification('File Load Failed', err.message, 'error');
    }
}

// Paste WKT
btnLoadWkt.addEventListener('click', async () => {
    const wkt = wktInput.value.trim();
    if (!wkt) {
        showNotification('Validation Error', 'Please paste a valid WKT string.', 'error');
        return;
    }

    try {
        const response = await fetch('/api/parse-wkt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wkt, filename: 'wkt_input.wkt' })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'WKT parsing error');
        }

        const geojson = await response.json();
        addGeoJsonToDrawnItems(geojson, 'WKT Geometry');
        wktInput.value = '';
        showNotification('Success', 'WKT Geometry loaded successfully.', 'success');
    } catch (err) {
        showNotification('WKT Load Failed', err.message, 'error');
    }
});

function addGeoJsonToDrawnItems(geojson, filename) {
    const layer = L.geoJSON(geojson, {
        style: {
            color: '#00f2fe',
            fillColor: 'rgba(0, 242, 254, 0.1)',
            weight: 2
        }
    });

    // Add each child layer
    layer.eachLayer((child) => {
        drawnItems.addLayer(child);
    });

    updateBoundariesList();
    
    // Zoom map to outer boundaries
    if (drawnItems.getLayers().length > 0) {
        map.fitBounds(drawnItems.getBounds(), { padding: [30, 30] });
    }
}

// Fetch available collections from Catalog/Glossary
async function fetchCollections() {
    collectionsListDiv.innerHTML = '<div class="loading-inline"><i class="fa-solid fa-spinner fa-spin"></i> Loading collections...</div>';
    
    try {
        const headers = {};
        const response = await fetch('/api/collections', { headers });
        if (!response.ok) throw new Error('Could not fetch catalog collections');
        
        const collections = await response.json();
        state.collections = collections;
        
        // Filter searchable collections
        const searchableCols = collections.filter(c => c.search_available);
        
        // Count each product type
        const countOpt = searchableCols.filter(c => c.product_type === 'OPTICAL').length;
        const countSar = searchableCols.filter(c => c.product_type === 'SAR').length;
        const countElev = searchableCols.filter(c => c.product_type === 'ELEVATION').length;
        
        // Update UI Counts
        countOPTICAL.innerText = countOpt;
        countSAR.innerText = countSar;
        countELEVATION.innerText = countElev;
        
        // Render currently active tab
        renderCollectionsList();

    } catch (err) {
        collectionsListDiv.innerHTML = `<p class="empty-list-text" style="color: var(--color-rose);"><i class="fa-solid fa-circle-exclamation"></i> Error loading collections.</p>`;
        showNotification('Collections Load Failed', err.message, 'error');
    }
    
    validateSearchReady();
}

// Render filtered collection items
function renderCollectionsList() {
    collectionsListDiv.innerHTML = '';
    
    const filteredCols = state.collections.filter(
        c => c.search_available && c.product_type === activeColTab
    );
    
    if (filteredCols.length === 0) {
        collectionsListDiv.innerHTML = `<p class="empty-list-text">No searchable collections under ${activeColTab} category.</p>`;
        return;
    }
    
    filteredCols.forEach(col => {
        const item = document.createElement('label');
        item.className = 'collection-checkbox-item';
        
        const isOptical = col.product_type === 'OPTICAL';
        const isElevation = col.product_type === 'ELEVATION';
        let icon = 'fa-satellite';
        if (isElevation) icon = 'fa-mountain-sun';
        else if (isOptical) icon = 'fa-camera-retro';
        
        const isChecked = state.selectedCollections.has(col.name) ? 'checked' : '';
        
        item.innerHTML = `
            <input type="checkbox" name="collections" value="${col.name}" ${isChecked}>
            <i class="fa-solid ${icon} icon-glow" style="margin-top: 3px;"></i>
            <div class="collection-checkbox-details">
                <span class="collection-checkbox-title">${col.title || col.name}</span>
                <span class="collection-checkbox-host">Host: ${col.host || 'Unknown'} | Type: ${col.type}</span>
            </div>
        `;
        
        const input = item.querySelector('input');
        input.addEventListener('change', (e) => {
            if (e.target.checked) {
                state.selectedCollections.add(col.name);
            } else {
                state.selectedCollections.delete(col.name);
            }
            validateSearchReady();
        });
        
        collectionsListDiv.appendChild(item);
    });
}

// Sub-tabs Click listeners
document.querySelectorAll('.col-tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.col-tab-btn').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        activeColTab = e.currentTarget.getAttribute('data-type');
        renderCollectionsList();
    });
});

// Select All in Active Tab
btnSelectAllCol.addEventListener('click', () => {
    const filteredCols = state.collections.filter(
        c => c.search_available && c.product_type === activeColTab
    );
    filteredCols.forEach(col => state.selectedCollections.add(col.name));
    renderCollectionsList();
    validateSearchReady();
});

// Deselect All in Active Tab
btnDeselectAllCol.addEventListener('click', () => {
    const filteredCols = state.collections.filter(
        c => c.search_available && c.product_type === activeColTab
    );
    filteredCols.forEach(col => state.selectedCollections.delete(col.name));
    renderCollectionsList();
    validateSearchReady();
});

// Form validation
function validateSearchReady() {
    const selectedCols = getSelectedCollections();
    const hasBoundaries = state.boundaries.length > 0;
    
    btnSearch.disabled = !(state.isConnected && hasBoundaries && selectedCols.length > 0);
}

function getSelectedCollections() {
    return Array.from(state.selectedCollections);
}

// Cloud cover slider updates
cloudCoverSlider.addEventListener('input', (e) => {
    cloudCoverValSpan.innerText = `${e.target.value}%`;
});

// Search Catalog
btnSearch.addEventListener('click', async () => {
    const selectedCols = getSelectedCollections();
    const boundariesCount = state.boundaries.length;
    
    if (selectedCols.length === 0 || boundariesCount === 0) return;

    // Get combined geometries as a single GeoJSON geometry (GeometryCollection)
    const geometries = state.boundaries.map(b => b.layer.toGeoJSON().geometry);
    let targetGeometry = null;

    if (geometries.length === 1) {
        targetGeometry = geometries[0];
    } else {
        targetGeometry = {
            "type": "GeometryCollection",
            "geometries": geometries
        };
    }

    const searchParams = {
        email: state.email,
        password: state.password,
        geometry: targetGeometry,
        collections: selectedCols,
        datetime: `${startDateInput.value}T00:00:00Z/${endDateInput.value}T23:59:59Z`,
        cloud_cover: parseInt(cloudCoverSlider.value),
        limit: parseInt(searchLimitSelect.value)
    };

    // Show Progress
    searchProgressOverlay.style.display = 'flex';
    btnSearch.disabled = true;
    btnSearch.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> QUERYING CATALOG...';
    
    // Clear old footprints
    sceneFootprints.clearLayers();
    state.sceneLayers = {};
    resultsListDiv.innerHTML = '';
    
    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(searchParams)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Catalog search failed');
        }

        const featureCollection = await response.json();
        state.searchResults = featureCollection;
        
        displayResults(featureCollection);
        
    } catch (err) {
        showNotification('Search Error', err.message, 'error');
        resultsListDiv.innerHTML = `
            <div class="empty-results-state">
                <i class="fa-solid fa-circle-exclamation text-rose" style="font-size: 3rem;"></i>
                <p style="color: var(--color-rose); font-weight: 500;">Search failed</p>
                <p>${err.message}</p>
            </div>
        `;
    } finally {
        searchProgressOverlay.style.display = 'none';
        btnSearch.disabled = false;
        btnSearch.innerHTML = '<i class="fa-solid fa-magnifying-glass-location"></i> SEARCH UP42 CATALOG';
    }
});

// Render foot-prints on map and lists on sidebar
function displayResults(fc) {
    const features = fc.features || [];
    resultsCountSpan.innerText = `${features.length} items`;
    resultsListDiv.innerHTML = '';

    if (features.length === 0) {
        resultsListDiv.innerHTML = `
            <div class="empty-results-state">
                <i class="fa-solid fa-satellite-dish placeholder-icon"></i>
                <p>No matching satellite scenes found for the selected boundaries and filters.</p>
            </div>
        `;
        resultsPanel.classList.remove('collapsed');
        return;
    }

    // Add layers to sceneFootprints
    features.forEach((feature, index) => {
        const id = feature.id || `scene-${index}`;
        const properties = feature.properties || {};
        
        // Footprint details
        const collection = properties.collection || properties.collection_name || 'N/A';
        const dateStr = properties.datetime || properties.acquisition_date || 'N/A';
        const formattedDate = dateStr !== 'N/A' ? new Date(dateStr).toLocaleString() : 'N/A';
        const cloudCover = properties['eo:cloud_cover'] !== undefined ? properties['eo:cloud_cover'] : properties.cloud_cover;
        const resolution = properties.resolution || properties['gsd'] || 'N/A';
        const sensor = properties.instrument || properties.sensor_type || 'N/A';
        const host = properties._host || 'N/A';

        // Find quicklook thumbnail
        const thumbUrl = getThumbnailUrl(feature);

        // Standard styling
        const defaultStyle = {
            color: '#a855f7', // Neon purple
            fillColor: 'rgba(168, 85, 247, 0.05)',
            weight: 1.5,
            opacity: 0.8,
            fillOpacity: 0.2
        };

        const hoverStyle = {
            color: '#00f2fe', // Neon cyan
            fillColor: 'rgba(0, 242, 254, 0.15)',
            weight: 3,
            opacity: 1.0,
            fillOpacity: 0.4
        };

        // Render polygon on map
        if (feature.geometry) {
            const geoLayer = L.geoJSON(feature, {
                style: defaultStyle,
                onEachFeature: (f, layer) => {
                    // Create Popup DOM Element programmatically to avoid ID escaping issues
                    const popupDiv = document.createElement('div');
                    popupDiv.style.fontFamily = 'var(--font-body)';
                    popupDiv.style.fontSize = '0.8rem';
                    popupDiv.style.lineHeight = '1.4';
                    popupDiv.style.maxWidth = '250px';
                    popupDiv.innerHTML = `
                        <strong style="color: var(--color-cyan); font-size: 0.85rem; font-family: var(--font-heading); display: block; margin-bottom: 6px;">
                            ${collection.toUpperCase()}
                        </strong>
                        ${thumbUrl ? `<img src="${thumbUrl}" style="width: 100%; max-height: 100px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color); margin-bottom: 8px;">` : ''}
                        <table style="width:100%; border-collapse:collapse;">
                            <tr><td style="color:var(--text-secondary); padding: 2px 0;">Date:</td><td style="font-weight:600; text-align:right;">${formattedDate.split(',')[0]}</td></tr>
                            <tr><td style="color:var(--text-secondary); padding: 2px 0;">Cloud:</td><td style="font-weight:600; text-align:right;">${cloudCover !== undefined ? cloudCover.toFixed(1) + '%' : 'N/A'}</td></tr>
                            <tr><td style="color:var(--text-secondary); padding: 2px 0;">Res:</td><td style="font-weight:600; text-align:right;">${resolution} m</td></tr>
                        </table>
                    `;
                    
                    const btnMetadata = document.createElement('button');
                    btnMetadata.className = 'btn btn-primary btn-block btn-sm';
                    btnMetadata.style.marginTop = '8px';
                    btnMetadata.innerText = 'Full Metadata';
                    btnMetadata.addEventListener('click', () => {
                        showSceneMetadata(id);
                    });
                    popupDiv.appendChild(btnMetadata);
                    
                    layer.bindPopup(popupDiv);
                    
                    // Hover effects
                    layer.on('mouseover', () => {
                        layer.setStyle(hoverStyle);
                        const cardElement = document.getElementById(`card-${id}`);
                        if (cardElement) cardElement.classList.add('active-scene-card');
                    });
                    
                    layer.on('mouseout', () => {
                        layer.setStyle(defaultStyle);
                        const cardElement = document.getElementById(`card-${id}`);
                        if (cardElement) cardElement.classList.remove('active-scene-card');
                    });
                }
            });
            
            sceneFootprints.addLayer(geoLayer);
            state.sceneLayers[id] = geoLayer;
        }

        // Add Card to Sidebar
        const card = document.createElement('div');
        card.className = 'scene-card';
        card.id = `card-${id}`;
        card.innerHTML = `
            <div class="scene-card-header">
                <span class="scene-collection">${collection}</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="scene-date">${formattedDate.split(',')[0]}</span>
                    <button class="btn-card-info" title="View Full Metadata" style="background:none; border:none; color:var(--color-cyan); cursor:pointer; padding:2px; font-size:0.85rem; display:flex; align-items:center; justify-content:center;"><i class="fa-solid fa-circle-info"></i></button>
                </div>
            </div>
            <div class="scene-card-body">
                <div class="scene-thumbnail-container">
                    ${thumbUrl ? `<img class="scene-thumbnail" src="${thumbUrl}" alt="thumbnail">` : '<i class="fa-solid fa-satellite scene-thumbnail-fallback"></i>'}
                </div>
                <div class="scene-details-quick">
                    <div class="scene-detail-row">
                        <span class="scene-detail-label">Cloud:</span>
                        <span class="scene-detail-val">${cloudCover !== undefined ? cloudCover.toFixed(1) + '%' : 'N/A'}</span>
                    </div>
                    <div class="scene-detail-row">
                        <span class="scene-detail-label">Resolution:</span>
                        <span class="scene-detail-val">${resolution} m</span>
                    </div>
                    <div class="scene-detail-row">
                        <span class="scene-detail-label">ID:</span>
                        <span class="scene-detail-val" title="${id}">${id}</span>
                    </div>
                </div>
            </div>
        `;

        // Card Hover effects
        card.addEventListener('mouseenter', () => {
            const geoLayer = state.sceneLayers[id];
            if (geoLayer) {
                geoLayer.setStyle(hoverStyle);
            }
        });

        card.addEventListener('mouseleave', () => {
            const geoLayer = state.sceneLayers[id];
            if (geoLayer) {
                geoLayer.setStyle(defaultStyle);
            }
        });

        // Click actions
        card.addEventListener('click', (e) => {
            const geoLayer = state.sceneLayers[id];
            if (geoLayer) {
                const bounds = geoLayer.getBounds();
                map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
                geoLayer.openPopup();
            }
        });

        // Info Button click
        const btnCardInfo = card.querySelector('.btn-card-info');
        if (btnCardInfo) {
            btnCardInfo.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent triggering map center/popup action
                showSceneMetadata(id);
            });
        }

        // Double click
        card.addEventListener('dblclick', () => {
            showSceneMetadata(id);
        });

        resultsListDiv.appendChild(card);
    });

    // Fit map bounds to show all footprints
    if (sceneFootprints.getLayers().length > 0) {
        map.fitBounds(sceneFootprints.getBounds(), { padding: [50, 50] });
    }

    // Slide in the results panel
    resultsPanel.classList.remove('collapsed');
}

function getThumbnailUrl(feature) {
    if (!feature.assets) return null;
    const keys = ['thumbnail', 'quicklook', 'preview', 'thumbnail_webp', 'visual'];
    for (let k of keys) {
        if (feature.assets[k] && feature.assets[k].href) {
            return feature.assets[k].href;
        }
    }
    // Check key containing thumbnail
    for (let key in feature.assets) {
        if (key.toLowerCase().includes('thumbnail') || key.toLowerCase().includes('quicklook')) {
            return feature.assets[key].href;
        }
    }
    return null;
}

// Display Scene Details Modal
function showSceneMetadata(id) {
    if (!state.searchResults || !state.searchResults.features) return;

    // Robust search: match either raw id or index-based fallback id
    const feature = state.searchResults.features.find((f, idx) => {
        const fId = f.id || `scene-${idx}`;
        return fId === id;
    });
    
    if (!feature) {
        console.error("Scene metadata not found for ID:", id);
        return;
    }

    const properties = feature.properties || {};
    const thumbUrl = getThumbnailUrl(feature);

    let rowsHtml = '';
    
    // Sort keys alphabetically
    const keys = Object.keys(properties).sort();
    
    keys.forEach(key => {
        // Skip private or object types for simple presentation
        const val = properties[key];
        if (key.startsWith('_') || typeof val === 'object') return;
        
        rowsHtml += `
            <tr>
                <th>${key}</th>
                <td>${val}</td>
            </tr>
        `;
    });

    metadataModalBody.innerHTML = `
        ${thumbUrl ? `<img class="modal-quicklook-preview" src="${thumbUrl}" alt="Quicklook">` : ''}
        <div style="font-weight:700; margin-bottom:12px; font-family:var(--font-heading);">Scene ID: <span class="text-cyan">${id}</span></div>
        <table class="metadata-table">
            <thead>
                <tr>
                    <th style="width:30%">Property</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
                ${rowsHtml}
            </tbody>
        </table>
    `;

    metadataModal.style.display = 'flex';
}
window.showSceneMetadata = showSceneMetadata;

btnMetadataModalClose.addEventListener('click', () => {
    metadataModal.style.display = 'none';
});

// Close Results Drawer
btnCloseResults.addEventListener('click', () => {
    resultsPanel.classList.add('collapsed');
});

// Filter results list in sidebar
resultFilterSearch.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const cards = resultsListDiv.querySelectorAll('.scene-card');
    
    cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        if (text.includes(term)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
});

// Export Results
btnExportGeoJson.addEventListener('click', () => {
    if (!state.searchResults) return;
    
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state.searchResults, null, 2));
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute("href", dataStr);
    dlAnchorElem.setAttribute("download", `cosmos_up42_search_${new Date().toISOString().split('T')[0]}.geojson`);
    dlAnchorElem.click();
});

btnExportCsv.addEventListener('click', () => {
    if (!state.searchResults || !state.searchResults.features) return;
    
    const features = state.searchResults.features;
    let csvContent = "data:text/csv;charset=utf-8,";
    
    // Headers
    csvContent += "Scene ID,Collection,Acquisition Date,Cloud Cover %,Resolution m,Sensor,Provider Host,Thumbnail URL\n";
    
    features.forEach(f => {
        const props = f.properties || {};
        const id = f.id || '';
        const collection = props.collection || props.collection_name || '';
        const date = props.datetime || props.acquisition_date || '';
        const cloud = props['eo:cloud_cover'] !== undefined ? props['eo:cloud_cover'] : (props.cloud_cover || '');
        const res = props.resolution || props['gsd'] || '';
        const sensor = props.instrument || props.sensor_type || '';
        const host = props._host || '';
        const thumb = getThumbnailUrl(f) || '';
        
        csvContent += `"${id}","${collection}","${date}",${cloud},"${res}","${sensor}","${host}","${thumb}"\n`;
    });
    
    const encodedUri = encodeURI(csvContent);
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute("href", encodedUri);
    dlAnchorElem.setAttribute("download", `cosmos_up42_report_${new Date().toISOString().split('T')[0]}.csv`);
    dlAnchorElem.click();
});

// Inline Alert Notification Helper
function showNotification(title, text, type = 'info') {
    // Standard alert implementation
    console.log(`[${type.toUpperCase()}] ${title}: ${text}`);
    
    // Optional: create a floating alert box in UI
    const container = document.body;
    const alertBox = document.createElement('div');
    
    let color = 'var(--color-cyan)';
    let icon = 'fa-circle-info';
    
    if (type === 'error') {
        color = 'var(--color-rose)';
        icon = 'fa-triangle-exclamation';
    } else if (type === 'success') {
        color = 'var(--color-emerald)';
        icon = 'fa-circle-check';
    }

    alertBox.style.position = 'fixed';
    alertBox.style.bottom = '20px';
    alertBox.style.right = '20px';
    alertBox.style.background = 'rgba(13, 19, 35, 0.9)';
    alertBox.style.backdropFilter = 'blur(10px)';
    alertBox.style.border = `1px solid ${color}`;
    alertBox.style.color = '#fff';
    alertBox.style.padding = '12px 18px';
    alertBox.style.borderRadius = '8px';
    alertBox.style.boxShadow = '0 5px 20px rgba(0,0,0,0.5)';
    alertBox.style.zIndex = '9999';
    alertBox.style.display = 'flex';
    alertBox.style.alignItems = 'center';
    alertBox.style.gap = '12px';
    alertBox.style.fontFamily = 'var(--font-body)';
    alertBox.style.fontSize = '0.82rem';
    alertBox.style.animation = 'fadeIn 0.2s ease-out';
    
    alertBox.innerHTML = `
        <i class="fa-solid ${icon}" style="color: ${color}; font-size: 1.1rem;"></i>
        <div>
            <strong style="display:block; font-family:var(--font-heading); font-size:0.88rem; margin-bottom: 2px;">${title}</strong>
            <span>${text}</span>
        </div>
    `;

    container.appendChild(alertBox);
    
    setTimeout(() => {
        alertBox.style.animation = 'fadeIn 0.2s reverse ease-out';
        setTimeout(() => alertBox.remove(), 200);
    }, 4000);
}

// Initial Fetch on app load
fetchCollections();
updateBoundariesList();
if (state.email) {
    showNotification('Configuration Loaded', 'Saved console email loaded from storage.', 'info');
}
