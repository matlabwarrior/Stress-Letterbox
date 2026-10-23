/* server/dashboard/static/js/heatmap.js
   Floor plan heatmap using Leaflet.js with image overlay
   and leaflet-heat plugin.

   Approach:
   - Leaflet CRS.Simple treats the floor plan image as a flat coordinate space
   - Coordinates stored as relative X/Y floats (0.0–1.0) are mapped to pixel coords
   - leaflet-heat renders intensity-weighted dots as a smooth heat layer
   - All filtering is done via API query params — data re-fetched on filter change
*/

const MAP_WIDTH  = 1000;  // Virtual pixel space for the CRS
const MAP_HEIGHT = 700;

let map = null;
let heatLayer = null;
let imageOverlay = null;
let floorplanLoaded = false;

// ── Initialise Leaflet map ─────────────────────────────────
function initMap() {
  const bounds = [[0, 0], [MAP_HEIGHT, MAP_WIDTH]];

  map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -2,
    maxZoom: 3,
    zoomSnap: 0.25,
  });

  // Try to load floor plan
  fetch('/api/floorplan')
    .then(res => {
      if (!res.ok) throw new Error('no floorplan');
      return res.blob();
    })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      imageOverlay = L.imageOverlay(url, bounds).addTo(map);
      map.fitBounds(bounds);
      floorplanLoaded = true;
      loadHeatmapData();
    })
    .catch(() => {
      document.getElementById('map').style.display = 'none';
      document.getElementById('no-floorplan-msg').style.display = 'block';
    });
}

// ── Fetch heatmap data from server ─────────────────────────
function loadHeatmapData() {
  const params = new URLSearchParams();
  const dept   = document.getElementById('f-dept').value;
  const level  = document.getElementById('f-level').value;
  const reason = document.getElementById('f-reason').value;
  const from   = document.getElementById('f-from').value;
  const to     = document.getElementById('f-to').value;

  if (dept)   params.set('department', dept);
  if (level)  params.set('stress_level', level);
  if (reason) params.set('reason_category', reason);
  if (from)   params.set('date_from', from);
  if (to)     params.set('date_to', to);

  const status = document.getElementById('hm-status');
  status.textContent = 'Loading…';

  fetch('/api/admin/heatmap-data?' + params.toString())
    .then(r => r.json())
    .then(data => {
      renderHeat(data.points);
      status.textContent = `${data.count} location-tagged entr${data.count === 1 ? 'y' : 'ies'} shown`;
    })
    .catch(err => {
      status.textContent = 'Error loading data.';
      console.error(err);
    });
}

// ── Render heat layer ──────────────────────────────────────
function renderHeat(points) {
  if (heatLayer) {
    map.removeLayer(heatLayer);
    heatLayer = null;
  }

  if (!points.length) return;

  // Convert relative (0–1) coords to pixel coords in our virtual space
  // Leaflet CRS.Simple: y=0 is bottom, so we invert y
  const leafletPoints = points.map(p => [
    MAP_HEIGHT * (1 - p.y),  // invert y
    MAP_WIDTH  * p.x,
    p.intensity,              // 0.0–1.0, already normalised by server
  ]);

  heatLayer = L.heatLayer(leafletPoints, {
    radius:  30,
    blur:    25,
    maxZoom: 3,
    max:     1.0,
    gradient: {
      0.2: '#a8c5a0',
      0.5: '#e8b96a',
      0.8: '#d4845a',
      1.0: '#b85c4a',
    }
  }).addTo(map);
}

// ── Floor plan upload ──────────────────────────────────────
document.getElementById('upload-btn').addEventListener('click', () => {
  const fileInput = document.getElementById('fp-file');
  const labelInput = document.getElementById('fp-label');
  const status = document.getElementById('upload-status');

  if (!fileInput.files.length) {
    status.textContent = 'Please select a file.';
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('label', labelInput.value);
  status.textContent = 'Uploading…';

  fetch('/api/floorplan/upload', {
    method: 'POST',
    body: formData,
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        status.textContent = 'Error: ' + data.error;
      } else {
        status.textContent = '✓ Uploaded. Reload the page to see the new floor plan.';
      }
    })
    .catch(() => { status.textContent = 'Upload failed.'; });
});

// ── Filter button ──────────────────────────────────────────
document.getElementById('hm-apply').addEventListener('click', () => {
  if (floorplanLoaded) loadHeatmapData();
});

// ── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', initMap);
