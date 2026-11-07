const $ = (s) => document.querySelector(s);

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}

function say(text, isError) {
  const el = $('#note');
  el.textContent = text;
  el.className = 'note' + (isError ? ' err' : '');
}

async function loadMenu() {
  const items = await api('/api/menu');
  $('#menu-grid').replaceChildren(
    ...items.map((m) => {
      const b = document.createElement('button');
      b.className = 'drink';
      const name = document.createElement('b');
      name.textContent = m.drink.replace('_', ' ');
      const price = document.createElement('span');
      price.textContent = `$${m.price.toFixed(2)}`;
      b.append(name, price);
      b.onclick = () => order(m.drink);
      return b;
    })
  );
}

async function order(drink) {
  const customer = $('#customer').value.trim() || 'guest';
  try {
    const o = await api('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ drink, customer }),
    });
    say(`Ticket #${o.id} placed. ${o.position} in line.`);
    loadTickets();
  } catch (e) {
    say(e.message, true);
  }
}

async function loadTickets() {
  try {
    const orders = await api('/api/orders/recent');
    $('#rail-empty').hidden = orders.length > 0;
    $('#tickets').replaceChildren(
      ...orders.map((o) => {
        const li = document.createElement('li');
        li.className = `ticket ${o.status}`;
        const d = document.createElement('span');
        d.className = 'drink-name';
        d.textContent = o.drink.replace('_', ' ');
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.textContent = o.status;
        const meta = document.createElement('span');
        meta.className = 'meta';
        meta.textContent = `#${o.id} for ${o.customer}`;
        li.append(d, chip, meta);
        return li;
      })
    );
  } catch { /* keep the old rail if the API hiccups */ }
}

async function loadChaos() {
  try {
    const c = await api('/api/chaos');
    const bad = c.slowdown > 1.5 || c.fail_rate > 0.1;
    const el = $('#machine');
    el.textContent = bad ? `machine: broken (x${c.slowdown} slow, ${Math.round(c.fail_rate * 100)}% fail)` : 'machine: healthy';
    el.className = 'chip ' + (bad ? 'bad' : 'good');
  } catch { /* ignore */ }
}

async function setChaos(slowdown, fail_rate) {
  await api('/api/chaos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slowdown, fail_rate }),
  });
  loadChaos();
}

$('#break').onclick = () => setChaos(4, 0.35);
$('#repair').onclick = () => setChaos(1, 0.03);

async function loadLinks() {
  try {
    const c = await api('/api/config');
    for (const [id, url] of [['#grafana', c.grafana_url], ['#prom', c.prometheus_url]]) {
      if (url) { $(id).href = url; $(id).hidden = false; }
    }
  } catch { /* ignore */ }
}

loadMenu();
loadTickets();
loadChaos();
loadLinks();
setInterval(loadTickets, 1500);
setInterval(loadChaos, 5000);
