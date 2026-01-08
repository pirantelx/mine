let containerChart = null;
const API_BASE = '/api';

// Получаем ID контейнера из URL
const containerId = window.location.pathname.split('/').pop();

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    loadContainerData();
    initializeChart();
});

// Загрузка данных контейнера
async function loadContainerData() {
    try {
        // Загружаем информацию о контейнере
        const containerResponse = await fetch(`${API_BASE}/containers/${containerId}`);
        const container = await containerResponse.json();
        
        document.getElementById('container-name').textContent = container.name;
        document.getElementById('container-description').textContent = container.description || 'Описание отсутствует';
        
        // Загружаем статистику контейнера
        const statsResponse = await fetch(`${API_BASE}/stats/containers/${containerId}?hours=1`);
        const statsData = await statsResponse.json();
        
        const containerStats = statsData.container_stats;
        document.getElementById('container-total-miners').textContent = containerStats.total_miners;
        document.getElementById('container-active-miners').textContent = containerStats.active_miners;
        document.getElementById('container-total-hashrate').textContent = formatHashrate(containerStats.total_hash_rate);
        document.getElementById('container-avg-temperature').textContent = containerStats.avg_temperature ? `${containerStats.avg_temperature.toFixed(1)}°C` : '-';
        document.getElementById('container-avg-power').textContent = containerStats.avg_power_consumption ? `${containerStats.avg_power_consumption.toFixed(1)}W` : '-';
        
        // Загружаем список майнеров
        const minersList = document.getElementById('miners-list');
        minersList.innerHTML = '';
        
        if (statsData.miner_stats && statsData.miner_stats.length > 0) {
            statsData.miner_stats.forEach(stat => {
                const card = document.createElement('div');
                card.className = 'miner-card';
                card.innerHTML = `
                    <h3>${stat.miner_name}</h3>
                    <p><strong>Хешрейт:</strong> ${formatHashrate(stat.hash_rate)}</p>
                    <p><strong>Температура:</strong> ${stat.temperature ? stat.temperature.toFixed(1) + '°C' : '-'}</p>
                    <p><strong>Скорость вентилятора:</strong> ${stat.fan_speed || '-'}</p>
                    <p><strong>Потребление:</strong> ${stat.power_consumption ? stat.power_consumption.toFixed(1) + 'W' : '-'}</p>
                    <p><strong>Принятые шары:</strong> ${stat.accepted_shares || 0}</p>
                    <p><strong>Отклоненные шары:</strong> ${stat.rejected_shares || 0}</p>
                    <p><strong>Обновлено:</strong> ${new Date(stat.timestamp).toLocaleString('ru-RU')}</p>
                `;
                minersList.appendChild(card);
            });
        } else {
            minersList.innerHTML = '<p>Нет данных о майнерах в этом контейнере</p>';
        }
        
        // Обновляем графики
        updateCharts();
    } catch (error) {
        console.error('Error loading container data:', error);
    }
}

// Инициализация графика
function initializeChart() {
    const ctx = document.getElementById('container-chart');
    containerChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
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
    const metric = document.getElementById('chart-metric').value;
    const hours = parseInt(document.getElementById('chart-hours').value);
    
    try {
        // Получаем всех майнеров в контейнере
        const minersResponse = await fetch(`${API_BASE}/miners?container_id=${containerId}`);
        const miners = await minersResponse.json();
        
        if (miners.length === 0) {
            return;
        }
        
        // Собираем данные для каждого майнера
        const datasets = [];
        const colors = [
            'rgb(52, 152, 219)',
            'rgb(46, 204, 113)',
            'rgb(241, 196, 15)',
            'rgb(231, 76, 60)',
            'rgb(155, 89, 182)',
            'rgb(26, 188, 156)',
            'rgb(230, 126, 34)',
            'rgb(52, 73, 94)'
        ];
        
        const allTimestamps = new Set();
        const minerData = {};
        
        for (let i = 0; i < miners.length; i++) {
            const miner = miners[i];
            const statsResponse = await fetch(`${API_BASE}/stats/miners/${miner.id}?hours=${hours}&limit=1000`);
            const stats = await statsResponse.json();
            
            if (stats.length === 0) continue;
            
            // Сортируем по времени
            stats.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            
            const data = [];
            stats.forEach(stat => {
                const timestamp = new Date(stat.timestamp).toISOString();
                allTimestamps.add(timestamp);
                data.push({ timestamp, value: stat[metric] || 0 });
            });
            
            minerData[miner.id] = {
                name: miner.name,
                data: data
            };
        }
        
        // Сортируем все временные метки
        const sortedTimestamps = Array.from(allTimestamps).sort();
        
        // Формируем датасеты для графика
        Object.keys(minerData).forEach((minerId, index) => {
            const data = minerData[minerId];
            const values = [];
            
            sortedTimestamps.forEach(ts => {
                const point = data.data.find(d => d.timestamp === ts);
                values.push(point ? point.value : null);
            });
            
            datasets.push({
                label: data.name,
                data: values,
                borderColor: colors[index % colors.length],
                backgroundColor: colors[index % colors.length].replace('rgb', 'rgba').replace(')', ', 0.1)'),
                tension: 0.1
            });
        });
        
        const labels = sortedTimestamps.map(ts => new Date(ts).toLocaleString('ru-RU'));
        
        let label = '';
        switch(metric) {
            case 'hash_rate':
                label = 'Хешрейт (TH/s)';
                break;
            case 'temperature':
                label = 'Температура (°C)';
                break;
            case 'power_consumption':
                label = 'Потребление энергии (W)';
                break;
        }
        
        containerChart.data.labels = labels;
        containerChart.data.datasets = datasets;
        containerChart.options.scales.y.title = { display: true, text: label };
        containerChart.update();
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
