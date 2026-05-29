(function () {
  const NIWA_HOSTS = new Set([
    '10.42.0.1',
    '192.168.1.100',
    '100.64.0.1',
    'niwahub.local',
    'niwahub.tailnet.ts.net'
  ]);

  const NIWA_PORTS = new Set([
    '3000',
    '5051',
    '5052',
    '5053',
    '5054',
    '5055',
    '5056',
    '8080',
    '61208',
    '9443'
  ]);

  function dynamicUrl(originalHref) {
    let url;
    try {
      url = new URL(originalHref, window.location.href);
    } catch (_error) {
      return null;
    }

    if (!NIWA_HOSTS.has(url.hostname) && !NIWA_PORTS.has(url.port)) {
      return null;
    }

    const nextProtocol = url.port === '9443' ? 'https:' : window.location.protocol;
    return `${nextProtocol}//${window.location.hostname}:${url.port}${url.pathname}${url.search}${url.hash}`;
  }

  function systemPanelUrl(path) {
    return `${window.location.protocol}//${window.location.hostname}:5056${path || ''}`;
  }

  function rewriteNiwaLinks() {
    document.querySelectorAll('a[href]').forEach((link) => {
      const href = link.getAttribute('href');
      const nextUrl = dynamicUrl(href);
      if (!nextUrl) {
        return;
      }

      if (!link.dataset.niwaOriginalHref) {
        link.dataset.niwaOriginalHref = href;
      }
      link.href = nextUrl;
    });
  }

  function statusClass(status) {
    if (status === 'ok') {
      return 'ok';
    }
    if (status === 'warning') {
      return 'warning';
    }
    return 'error';
  }

  function statusMark(status) {
    if (status === 'ok') {
      return 'OK';
    }
    if (status === 'warning') {
      return '!';
    }
    return 'X';
  }

  function statusLabel(status) {
    if (status === 'ok') {
      return 'NIWA OK';
    }
    if (status === 'warning') {
      return 'NIWA attenzione';
    }
    return 'NIWA verifica';
  }

  function ensureSystemBadge() {
    let badge = document.getElementById('niwa-system-badge');
    if (badge) {
      return badge;
    }

    badge = document.createElement('a');
    badge.id = 'niwa-system-badge';
    badge.href = systemPanelUrl('/');
    badge.innerHTML = [
      '<span class="niwa-system-mark">...</span>',
      '<span class="niwa-system-copy">',
      '<strong>NIWA System</strong>',
      '<small>Controllo stato</small>',
      '</span>'
    ].join('');
    document.body.appendChild(badge);
    return badge;
  }

  async function refreshSystemBadge() {
    const badge = ensureSystemBadge();
    const mark = badge.querySelector('.niwa-system-mark');
    const title = badge.querySelector('strong');
    const detail = badge.querySelector('small');

    try {
      const response = await fetch(systemPanelUrl('/api/summary'), { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      const state = statusClass(data.overall.status);
      badge.className = state;
      mark.textContent = statusMark(data.overall.status);
      title.textContent = statusLabel(data.overall.status);
      detail.textContent = data.overall.message;
    } catch (_error) {
      badge.className = 'error';
      mark.textContent = 'X';
      title.textContent = 'NIWA verifica';
      detail.textContent = 'System Panel non raggiungibile';
    }
  }

  document.addEventListener('click', function (event) {
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link) {
      return;
    }

    const href = link.dataset.niwaOriginalHref || link.getAttribute('href');
    const nextUrl = dynamicUrl(href);
    if (!nextUrl) {
      return;
    }

    event.preventDefault();
    window.location.href = nextUrl;
  }, true);

  setInterval(rewriteNiwaLinks, 2000);
  setInterval(refreshSystemBadge, 15000);
  window.addEventListener('DOMContentLoaded', function () {
    rewriteNiwaLinks();
    refreshSystemBadge();
  });
  window.addEventListener('load', function () {
    rewriteNiwaLinks();
    refreshSystemBadge();
  });
})();
