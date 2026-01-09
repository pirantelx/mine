let siteChart = null;
const API_BASE = '/api';

// Получаем ID площадки из URL
const siteId = window.location.pathname.split('/').pop();

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    loadSiteData();
    initializeChart();
});

// Загрузка данных площадки
async function loadSiteData() {
    try {
        // Загружаем информацию о площадке
        const siteResponse = await fetch(`${API_BASE}/sites/${siteId}`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        
        if (siteResponse.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        if (!siteResponse.ok) {
            throw new Error('Failed to load site data');
        }
        
        const site = await siteResponse.json();
        
        // Обновляем заголовок
        document.getElementById('site-name').textContent = site.name;
        document.getElementById('site-description').textContent = site.description || '';
        document.getElementById('site-location').textContent = site.location ? `Местоположение: ${site.location}` : '';
        
        // Загружаем статистику площадки
        const statsResponse = await fetch(`${API_BASE}/stats/sites/${siteId}`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        
        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            document.getElementById('site-total-containers').textContent = stats.total_containers || 0;
            document.getElementById('site-total-miners').textContent = stats.total_miners || 0;
            document.getElementById('site-active-miners').textContent = stats.active_miners || 0;
            document.getElementById('site-total-hashrate').textContent = formatHashrate(stats.total_hash_rate);
            document.getElementById('site-avg-temperature').textContent = stats.avg_temperature 
                ? `${stats.avg_temperature.toFixed(1)} °C` 
                : '-';
            document.getElementById('site-avg-power').textContent = stats.avg_power_consumption 
                ? `${stats.avg_power_consumption.toFixed(1)} W` 
                : '-';
        }
        
        // Загружаем контейнеры на площадке
        const containersResponse = await fetch(`${API_BASE}/containers?site_id=${siteId}`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        
        if (containersResponse.ok) {
            const containers = await containersResponse.json();
            const containersList = document.getElementById('containers-list');
            containersList.innerHTML = '';
            
            containers.forEach(container => {
                const card = document.createElement('div');
                card.className = 'container-card';
                card.innerHTML = `
                    <h3>${container.name}</h3>
                    <p><strong>Майнеров:</strong> ${container.miner_count || 0}</p>
                    <p><strong>Местоположение:</strong> ${container.location || 'Не указано'}</p>
                    <div class="action-buttons">
                        <button onclick="location.href='/containers/${container.id}'">Подробнее</button>
                    </div>
                `;
                containersList.appendChild(card);
            });
        }
        
        // Обновляем графики
        updateCharts();
    } catch (error) {
        console.error('Error loading site data:', error);
    }
}

// Инициализация графика
function initializeChart() {
    const ctx = document.getElementById('site-chart');
    if (!ctx) return;
    
    siteChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Метрика',
                data: [],
                borderColor: 'rgb(52, 152, 219)',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Обновление графиков
async function updateCharts() {
    if (!siteChart) return;
    
    const metric = document.getElementById('chart-metric').value;
    const hours = parseInt(document.getElementById('chart-hours').value) || 24;
    
    try {
        // Загружаем статистику за указанный период
        const response = await fetch(`${API_BASE}/stats/sites/${siteId}?hours=${hours}`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        
        if (!response.ok) return;
        
        // Здесь можно добавить загрузку исторических данных для графика
        // Пока просто обновляем метку
        const labels = {
            'hash_rate': 'Общий хешрейт (TH/s)',
            'temperature': 'Средняя температура (°C)',
            'power_consumption': 'Среднее потребление (W)'
        };
        
        siteChart.data.datasets[0].label = labels[metric] || 'Метрика';
        siteChart.update();
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}

// Утилиты
function formatHashrate(hashrate) {
    if (!hashrate || hashrate === 0) return '-';
    if (hashrate >= 1000) {
        return `${(hashrate / 1000).toFixed(2)} PH/s`;
    }
    return `${hashrate.toFixed(2)} TH/s`;
}

function getAuthHeaders() {
    let token = localStorage.getItem('access_token');
    
    if (!token) {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'access_token') {
                token = value;
                localStorage.setItem('access_token', token);
                break;
            }
        }
    }
    
    if (!token) {
        window.location.href = '/login';
        return {};
    }
    
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}
