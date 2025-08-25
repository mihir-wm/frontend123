function backendBase() {
  const fromStorage = (window.BACKEND_URL || '').trim();
  const input = document.getElementById('backendUrl');
  const val = (input && input.value.trim()) || fromStorage;
  return val || '';
}

function endpoint(path) {
  const base = backendBase();
  if (!base) return path; // same-origin
  return base.replace(/\/$/, '') + path;
}

function setStoredBackend(url) {
  localStorage.setItem('BACKEND_URL', url || '');
  window.BACKEND_URL = url || '';
}

document.addEventListener('DOMContentLoaded', () => {
  const backendUrl = localStorage.getItem('BACKEND_URL') || '';
  const backendInput = document.getElementById('backendUrl');
  if (backendInput) backendInput.value = backendUrl;

  const saveBtn = document.getElementById('saveBackend');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const url = (backendInput.value || '').trim();
      setStoredBackend(url);
      alert('Backend URL saved');
    });
  }

  const ytUrl = document.getElementById('ytUrl');
  const btnHeader = document.getElementById('btnHeader');
  const btnRes = document.getElementById('btnRes');
  const headerDiv = document.getElementById('headerHtml');
  const resOut = document.getElementById('resOut');

  async function postJSON(url, data) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {})
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
  }

  if (btnHeader) {
    btnHeader.addEventListener('click', async () => {
      headerDiv.innerHTML = 'Loading...';
      try {
        const data = await postJSON(endpoint('/api/header'), { url: ytUrl.value || '' });
        headerDiv.innerHTML = data.html || '';
      } catch (e) {
        headerDiv.innerHTML = 'Error: ' + (e.message || e);
      }
    });
  }

  if (btnRes) {
    btnRes.addEventListener('click', async () => {
      resOut.textContent = 'Loading...';
      try {
        const data = await postJSON(endpoint('/api/resolutions'), { url: ytUrl.value || '' });
        resOut.textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        resOut.textContent = 'Error: ' + (e.message || e);
      }
    });
  }
});


