/* Coffee Matrix Dashboard JS */
let charts = { bar: null, pie: null, line: null };
let currentFilter = 'all';

async function fetchData(showLoader=true){
  const btn = document.getElementById('btn-refresh');
  if(showLoader){ btn.classList.add('disabled'); btn.querySelector('i').classList.add('spin'); }
  try {
    console.debug('[CoffeeMatrix] Fetching /api/data ...');
    const res = await fetch('/api/data', { cache: 'no-store' });
    const data = await res.json();
    console.debug('[CoffeeMatrix] Data received', data);
    updateMetrics(data.metrics);
    updateTables(data.stock_table, data.movements);
    updateCharts(data.charts);
  } catch(err){ console.error('Erro ao buscar dados', err); }
  finally {
    if(showLoader){ btn.classList.remove('disabled'); btn.querySelector('i').classList.remove('spin'); }
  }
}

function updateMetrics(m){
  document.getElementById('metric-itens').textContent = m.total_itens.toLocaleString('pt-BR');
  document.getElementById('metric-valor').textContent = m.valor_estimado;
  document.getElementById('metric-mov').textContent = m.movimentos_recent;
  document.getElementById('metric-brindes').textContent = m.total_brindes;
}

function updateTables(stock, movs){
  const stockBody = document.getElementById('stock-body');
  const movBody = document.getElementById('movements-body');
  stockBody.innerHTML='';
  movBody.innerHTML='';

  const filteredStock = stock.filter(r => filterRow(r));
  filteredStock.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><strong>${r.nome}</strong><br><small class="text-muted">${r.categoria||''}</small></td>
      <td class="text-center">${r.quantidade}</td>
      <td style="min-width:130px"><div class="progress"><div class="progress-bar" style="width:0%" data-q="${r.quantidade}"></div></div></td>
      <td class="text-end">R$ ${(r.preco).toFixed(2).replace('.',',')}</td>
      <td class="text-end">R$ ${(r.valor_total).toFixed(2).replace('.',',')}</td>`;
    stockBody.appendChild(tr);
  });

  // Set progress width relative to max
  const maxQ = Math.max(...filteredStock.map(r=>r.quantidade),1);
  stockBody.querySelectorAll('.progress-bar').forEach(el=>{
    const q = parseFloat(el.getAttribute('data-q'))||0;
    const pct = Math.round((q/maxQ)*100);
    el.style.width = pct + '%';
  });

  const filteredMovs = movs.filter(r => filterMovement(r));
  filteredMovs.forEach(m => {
    const dateLabel = new Date(m.data).toLocaleString('pt-BR',{ day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
    const tr = document.createElement('tr');
    tr.className = m.is_brinde? 'row-brinde':'';
    tr.innerHTML = `<td><small>${dateLabel}</small></td>
      <td>${m.is_brinde?'<span class="badge bg-warning text-dark">BRINDE</span> ':''}<strong>${m.nome}</strong><br><small class="text-muted">${m.tipo}</small></td>
      <td class="text-center">${m.tipo==='entrada'?'+':'-'}${m.quantidade}</td>
      <td class="text-end">${m.is_brinde || m.tipo==='entrada' ? '<span class="text-muted">—</span>' : 'R$ '+ (m.quantidade).toFixed(2).replace('.',',')}</td>`;
    movBody.appendChild(tr);
  });
}

function filterRow(r){
  if(currentFilter==='all') return true;
  if(currentFilter==='cafes') return r.categoria==='cafes';
  if(currentFilter==='embalagens') return r.categoria==='embalagens';
  if(currentFilter==='brindes') return false; // stock does not list brindes separately
  return true;
}
function filterMovement(m){
  if(currentFilter==='all') return true;
  if(currentFilter==='cafes') return m.categoria==='cafes' && !m.is_brinde;
  if(currentFilter==='embalagens') return m.categoria==='embalagens';
  if(currentFilter==='brindes') return m.is_brinde;
  return true;
}

function placeholderIfEmpty(labels, values){
  if(labels.length === 0){
    return { labels: ['Sem dados'], values: [0] };
  }
  return { labels, values };
}

function initCharts(ch){
  const barCtx = document.getElementById('chart-bar');
  const pieCtx = document.getElementById('chart-pie');
  const lineCtx = document.getElementById('chart-line');

  const pieProcessed = placeholderIfEmpty(ch.pie.labels, ch.pie.data);

  charts.bar = new Chart(barCtx, {
    type: 'bar',
    data: { labels: ch.bar.labels, datasets: [{ label: 'Quantidade', data: ch.bar.data, backgroundColor: 'rgba(201,168,106,0.7)' }] },
    options: { responsive: true, plugins:{ legend:{ labels:{ color:'#ccc' } } }, scales:{ x:{ ticks:{ color:'#ccc' }}, y:{ ticks:{ color:'#ccc' } } } }
  });

  charts.pie = new Chart(pieCtx, {
    type: 'pie',
    data: { labels: pieProcessed.labels, datasets: [{ data: pieProcessed.values, backgroundColor: pieProcessed.labels.map(()=>['#C9A86A','#4E342E','#8d6e63','#d7ccc8'][Math.floor(Math.random()*4)]) }] },
    options: { plugins:{ legend:{ labels:{ color:'#ccc' } } } }
  });

  charts.line = new Chart(lineCtx, {
    type: 'line',
    data: { labels: ch.line.labels, datasets: [
      { label:'Entradas', data: ch.line.entrada, borderColor:'#4caf50', tension:.3 },
      { label:'Saídas', data: ch.line.saida, borderColor:'#f44336', tension:.3 },
      { label:'Brindes', data: ch.line.brinde, borderColor:'#C9A86A', tension:.3 }
    ] },
    options: { plugins:{ legend:{ labels:{ color:'#ccc' } } }, scales:{ x:{ ticks:{ color:'#ccc' } }, y:{ ticks:{ color:'#ccc' } } } }
  });
}

function updateCharts(ch){
  if(!charts.bar){ initCharts(ch); return; }
  charts.bar.data.labels = ch.bar.labels;
  charts.bar.data.datasets[0].data = ch.bar.data;
  charts.bar.update();

  const pieProcessed = (ch.pie.labels.length? {labels: ch.pie.labels, values: ch.pie.data} : {labels:['Sem dados'], values:[0]});
  charts.pie.data.labels = pieProcessed.labels;
  charts.pie.data.datasets[0].data = pieProcessed.values;
  charts.pie.update();

  charts.line.data.labels = ch.line.labels;
  charts.line.data.datasets[0].data = ch.line.entrada;
  charts.line.data.datasets[1].data = ch.line.saida;
  charts.line.data.datasets[2].data = ch.line.brinde;
  charts.line.update();
}

function applyFilter(f){
  currentFilter = f;
  document.querySelectorAll('[data-filter]').forEach(btn => btn.classList.remove('active'));
  const target = document.querySelector(`[data-filter="${f}"]`);
  if(target) target.classList.add('active');
  fetchData(false);
}

function toggleTheme(){
  const root = document.documentElement;
  const isLight = root.classList.toggle('light');
  localStorage.setItem('cm-theme', isLight? 'light':'dark');
  document.getElementById('theme-icon').textContent = isLight? '🌙':'☀️';
}

function restoreTheme(){
  const saved = localStorage.getItem('cm-theme');
  if(saved==='light') document.documentElement.classList.add('light');
  document.getElementById('theme-icon').textContent = saved==='light'? '🌙':'☀️';
}

window.addEventListener('DOMContentLoaded', () => {
  restoreTheme();
  fetchData();
  setInterval(()=> fetchData(false), 30000); // auto refresh 30s
  document.getElementById('btn-refresh').addEventListener('click', ()=> fetchData(true));
  document.querySelectorAll('[data-filter]').forEach(btn => btn.addEventListener('click', () => applyFilter(btn.getAttribute('data-filter'))));
  document.getElementById('btn-theme').addEventListener('click', toggleTheme);
});
