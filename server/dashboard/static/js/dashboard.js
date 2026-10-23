/* server/dashboard/static/js/dashboard.js
   Chart.js visualisations for the admin overview dashboard.
*/

const PALETTE = {
  level: ['#a8c5a0', '#d4c88a', '#e8b96a', '#d4845a', '#b85c4a'],
  dept:  ['#7c9fba', '#a8c5a0', '#d4c88a', '#b89fc0', '#e8b96a',
          '#a0bac8', '#c8a8a0', '#9fbaa8', '#d4c88a', '#b8a87c'],
  grid:  'rgba(0,0,0,0.05)',
  text:  '#6b6560',
};

const CHART_DEFAULTS = {
  font: { family: "'DM Sans', sans-serif", size: 12 },
  color: PALETTE.text,
};

Chart.defaults.font = CHART_DEFAULTS.font;
Chart.defaults.color = CHART_DEFAULTS.color;

// ── Trend chart ────────────────────────────────────────────
(function buildTrend() {
  const ctx = document.getElementById('trend-chart');
  if (!ctx || !TREND_DATA.length) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: TREND_DATA.map(d => d.day),
      datasets: [{
        label: 'Entries',
        data: TREND_DATA.map(d => d.count),
        backgroundColor: 'rgba(124, 111, 94, 0.25)',
        borderColor: 'rgba(124, 111, 94, 0.7)',
        borderWidth: 1.5,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: PALETTE.grid },
          ticks: { maxTicksLimit: 10 },
        },
        y: {
          grid: { color: PALETTE.grid },
          beginAtZero: true,
          ticks: { precision: 0 },
        }
      }
    }
  });
})();

// ── Stress level doughnut ──────────────────────────────────
(function buildLevelChart() {
  const ctx = document.getElementById('level-chart');
  if (!ctx) return;

  const labels = ['1 — Low', '2 — Mild', '3 — Moderate', '4 — High', '5 — Intense'];
  const data = [1,2,3,4,5].map(l => BY_LEVEL[l] || 0);

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: PALETTE.level,
        borderWidth: 2,
        borderColor: '#ffffff',
      }]
    },
    options: {
      responsive: true,
      cutout: '60%',
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 12, padding: 14 } }
      }
    }
  });
})();

// ── Department bar chart ───────────────────────────────────
(function buildDeptChart() {
  const ctx = document.getElementById('dept-chart');
  if (!ctx) return;

  const depts = DEPT_NAMES.map(d => d.name);
  const counts = DEPT_NAMES.map(d => BY_DEPT[d.id] || 0);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: depts,
      datasets: [{
        label: 'Entries',
        data: counts,
        backgroundColor: PALETTE.dept,
        borderRadius: 4,
        borderWidth: 0,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: PALETTE.grid }, ticks: { precision: 0 } },
        y: { grid: { display: false } }
      }
    }
  });
})();

// ── Reason categories bar chart ────────────────────────────
(function buildReasonChart() {
  const ctx = document.getElementById('reason-chart');
  if (!ctx) return;

  // Sort by count descending
  const cats = REASON_CATS.map(c => ({
    id: c.id, label: c.label, count: BY_REASON[c.id] || 0
  })).sort((a, b) => b.count - a.count);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cats.map(c => c.label),
      datasets: [{
        label: 'Entries',
        data: cats.map(c => c.count),
        backgroundColor: 'rgba(124, 111, 94, 0.3)',
        borderColor: 'rgba(124, 111, 94, 0.8)',
        borderWidth: 1.5,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: PALETTE.grid }, beginAtZero: true, ticks: { precision: 0 } }
      }
    }
  });
})();
