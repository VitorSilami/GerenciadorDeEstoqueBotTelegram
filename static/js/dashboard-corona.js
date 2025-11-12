// ============================================
// DASHBOARD CORONA - EOS CAFÉS ESPECIAIS
// JavaScript para integração com APIs
// ============================================

// Estado global
let chart = null;
const API_ENDPOINTS = {
    dashboard: '/api/dashboard',
    produtos: '/api/produtos',
    vendas: '/api/vendas'
};

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    initializeNavigation();
    initializeRefreshButton();
    loadDashboardData();
    
    // Auto-refresh a cada 60s
    setInterval(loadDashboardData, 60000);
});

// ============================================
// TEMA (DARK/LIGHT)
// ============================================
function initializeTheme() {
    const themeToggle = document.getElementById('themeToggle');
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
    
    themeToggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme);
    });
}

function updateThemeIcon(theme) {
    const icon = document.querySelector('#themeToggle i');
    icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
}

// ============================================
// NAVEGAÇÃO
// ============================================
function initializeNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            const view = item.dataset.view;
            // Futuramente: trocar views (dashboard, estoque, vendas, histórico)
            console.log(`Navegando para: ${view}`);
        });
    });
}

// ============================================
// BOTÃO REFRESH
// ============================================
function initializeRefreshButton() {
    const refreshBtn = document.getElementById('refreshBtn');
    refreshBtn.addEventListener('click', () => {
        refreshBtn.classList.add('loading');
        loadDashboardData();
    });
}

// ============================================
// CARREGAMENTO DE DADOS
// ============================================
async function loadDashboardData() {
    try {
        const [dashboardData, produtosData, vendasData] = await Promise.all([
            fetchAPI(API_ENDPOINTS.dashboard),
            fetchAPI(API_ENDPOINTS.produtos),
            fetchAPI(API_ENDPOINTS.vendas)
        ]);
        
        updateKPICards(dashboardData, produtosData, vendasData);
        updateDonutChart(dashboardData, vendasData);
        updateStockTable(produtosData);
        updateBottomKPIs(vendasData);
        updateTimestamp();
        
        // Remove loading do botão refresh
        document.getElementById('refreshBtn').classList.remove('loading');
    } catch (error) {
        console.error('Erro ao carregar dados:', error);
        showError('Erro ao carregar dados do dashboard');
        document.getElementById('refreshBtn').classList.remove('loading');
    }
}

async function fetchAPI(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
}

// ============================================
// KPI CARDS SUPERIORES
// ============================================
function updateKPICards(dashboard, produtos, vendas) {
    // 1. Vendas Totais (R$)
    const vendasMes = dashboard?.vendas_mes || vendas?.totals?.month || 0;
    document.getElementById('vendasTotais').textContent = formatCurrency(vendasMes);
    
    // 2. Itens em Estoque (Unidades)
    const totalEstoque = produtos?.items?.reduce((sum, p) => sum + (p.quantidade || 0), 0) || 0;
    document.getElementById('itensEstoque').textContent = `${Math.floor(totalEstoque)} Unidades`;
    
    // 3. Vendas Hoje (Unidades)
    const vendasHoje = dashboard?.vendas_hoje || vendas?.totals?.day || 0;
    // Convertendo de R$ para unidades aproximadas (média R$ 30/item)
    const unidadesHoje = Math.floor(vendasHoje / 30);
    document.getElementById('vendasHoje').textContent = `${unidadesHoje} Unidades`;
    
    // 4. Alertas de Estoque (itens com qtd < 20)
    const alertas = produtos?.items?.filter(p => p.quantidade < 20).length || 0;
    document.getElementById('alertasEstoque').textContent = `${alertas} Itens Baixos`;
}

// ============================================
// GRÁFICO DE DONUT (VENDAS POR CATEGORIA)
// ============================================
function updateDonutChart(dashboard, vendas) {
    const ctx = document.getElementById('vendasCategoriaChart');
    if (!ctx) return;
    
    // Dados de vendas por categoria
    const categorias = dashboard?.vendas_categoria || vendas?.por_categoria || {};
    const labels = categorias.labels || ['Cafés', 'Embalagens', 'Brindes'];
    const values = categorias.values || [0, 0, 0];
    
    // Se já existe um gráfico, destruir antes de criar novo
    if (chart) chart.destroy();
    
    chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    'rgba(139, 92, 246, 0.8)',  // Roxo (Cafés)
                    'rgba(59, 130, 246, 0.8)',  // Azul (Embalagens)
                    'rgba(16, 185, 129, 0.8)'   // Verde (Brindes)
                ],
                borderColor: [
                    'rgba(139, 92, 246, 1)',
                    'rgba(59, 130, 246, 1)',
                    'rgba(16, 185, 129, 1)'
                ],
                borderWidth: 2,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e2e8f0',
                        font: { size: 13, weight: '600' },
                        padding: 16,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 26, 46, 0.95)',
                    titleColor: '#e2e8f0',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = formatCurrency(context.parsed);
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percent = ((context.parsed / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percent}%)`;
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// ============================================
// TABELA DE ESTOQUE
// ============================================
function updateStockTable(produtos) {
    const tbody = document.getElementById('estoqueTableBody');
    if (!tbody || !produtos?.items) return;
    
    // Limitar aos 10 produtos principais (maior estoque)
    const topProdutos = produtos.items
        .sort((a, b) => b.quantidade - a.quantidade)
        .slice(0, 10);
    
    tbody.innerHTML = topProdutos.map(produto => {
        const status = getStockStatus(produto.quantidade);
        const statusBadge = `<span class="status-badge ${status.class}">${status.icon} ${status.text}</span>`;
        
        return `
            <tr>
                <td><strong>${produto.nome}</strong></td>
                <td>${formatCategoria(produto.categoria)}</td>
                <td>${produto.quantidade.toFixed(1)} ${produto.unidade}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    }).join('');
}

function getStockStatus(quantidade) {
    if (quantidade > 50) {
        return { class: 'ok', text: 'OK', icon: '🟢' };
    } else if (quantidade >= 20) {
        return { class: 'baixo', text: 'Baixo', icon: '🟡' };
    } else {
        return { class: 'critico', text: 'Crítico', icon: '🔴' };
    }
}

// ============================================
// KPI CARDS INFERIORES (VENDAS POR CATEGORIA)
// ============================================
function updateBottomKPIs(vendas) {
    if (!vendas?.por_categoria) return;
    
    const labels = vendas.por_categoria.labels || [];
    const values = vendas.por_categoria.values || [];
    
    // Mapear índices de cada categoria
    const cafesIdx = labels.findIndex(l => l.toLowerCase().includes('cafe'));
    const embIdx = labels.findIndex(l => l.toLowerCase().includes('embalagem'));
    const brindesIdx = labels.findIndex(l => l.toLowerCase().includes('brinde'));
    
    document.getElementById('vendasCafes').textContent = 
        formatCurrency(cafesIdx >= 0 ? values[cafesIdx] : 0);
    
    document.getElementById('vendasEmbalagens').textContent = 
        formatCurrency(embIdx >= 0 ? values[embIdx] : 0);
    
    document.getElementById('vendasBrindes').textContent = 
        formatCurrency(brindesIdx >= 0 ? values[brindesIdx] : 0);
}

// ============================================
// UTILITÁRIOS
// ============================================
function formatCurrency(value) {
    if (value === null || value === undefined) return 'R$ 0,00';
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(value);
}

function formatCategoria(categoria) {
    const map = {
        'cafes': 'Cafés',
        'embalagens': 'Embalagens',
        'brindes': 'Brindes',
        'insumos': 'Insumos'
    };
    return map[categoria] || categoria;
}

function updateTimestamp() {
    const now = new Date();
    const formatted = now.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
    document.getElementById('lastUpdate').textContent = `Atualizado às ${formatted}`;
}

function showError(message) {
    // Implementar toast/notificação de erro (futuro)
    console.error(message);
}
