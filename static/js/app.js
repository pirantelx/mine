let statsChart = null;
const API_BASE = '/api';

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    loadOverview();
    loadContainers();
    loadMiners();
    initializeChart();
    setupContainersList();
});

// Загрузка общей статистики
async function loadOverview() {
    try {
        const containersResponse = await fetch(`${API_BASE}/containers`);
        const containers = await containersResponse.json();
        
        const minersResponse = await fetch(`${API_BASE}/miners`);
        const miners = await minersResponse.json();
        
        const overviewResponse = await fetch(`${API_BASE}/stats/overview`);
        const overview = await overviewResponse.json();
        
        document.getElementById('total-containers').textContent = containers.length;
        document.getElementById('total-miners').textContent = miners.length;
        document.getElementById('active-miners').textContent = miners.filter(m => m.is_active).length;
        
        const totalHashrate = overview.reduce((sum, c) => sum + (c.total_hash_rate || 0), 0);
        document.getElementById('total-hashrate').textContent = formatHashrate(totalHashrate);
    } catch (error) {
        console.error('Error loading overview:', error);
    }
}

// Загрузка списка контейнеров
async function loadContainers() {
    try {
        const response = await fetch(`${API_BASE}/containers`);
        const containers = await response.json();
        
        const containerList = document.getElementById('containers-list');
        containerList.innerHTML = '';
        
        const containerFilter = document.getElementById('container-filter');
        const containerSelect = document.querySelector('#add-miner-form select[name="container_id"]');
        
        // Очищаем select'ы, кроме первого элемента
        containerFilter.innerHTML = '<option value="">Все контейнеры</option>';
        containerSelect.innerHTML = '<option value="">Не выбран</option>';
        
        containers.forEach(container => {
            // Добавляем в список
            const card = document.createElement('div');
            card.className = 'container-card';
            card.innerHTML = `
                <h3>${container.name}</h3>
                <p><strong>Майнеров:</strong> ${container.miner_count}</p>
                <p><strong>Местоположение:</strong> ${container.location || 'Не указано'}</p>
                <div class="action-buttons">
                    <button onclick="location.href='/containers/${container.id}'">Подробнее</button>
                </div>
            `;
            containerList.appendChild(card);
            
            // Добавляем в фильтр
            const option1 = document.createElement('option');
            option1.value = container.id;
            option1.textContent = container.name;
            containerFilter.appendChild(option1);
            
            // Добавляем в форму
            const option2 = option1.cloneNode(true);
            containerSelect.appendChild(option2);
        });
    } catch (error) {
        console.error('Error loading containers:', error);
    }
}

// Загрузка списка майнеров
async function loadMiners() {
    try {
        const containerId = document.getElementById('container-filter').value;
        let url = `${API_BASE}/miners`;
        if (containerId) {
            url += `?container_id=${containerId}`;
        }
        
        const response = await fetch(url);
        const miners = await response.json();
        
        const tbody = document.getElementById('miners-tbody');
        tbody.innerHTML = '';
        
        const chartSelect = document.getElementById('chart-miner-select');
        chartSelect.innerHTML = '<option value="">Выберите майнер</option>';
        
        miners.forEach(miner => {
            const row = document.createElement('tr');
            const manufacturerModel = miner.manufacturer && miner.model 
                ? `${miner.manufacturer} ${miner.model}` 
                : (miner.manufacturer || '-');
            row.innerHTML = `
                <td>${miner.id}</td>
                <td>${miner.name}</td>
                <td>${manufacturerModel}</td>
                <td>${miner.ip_address}:${miner.port}</td>
                <td>${miner.container_name || '-'}</td>
                <td>-</td>
                <td>-</td>
                <td>${miner.last_seen ? new Date(miner.last_seen).toLocaleString('ru-RU') : 'Никогда'}</td>
                <td><span class="status-badge ${miner.is_active ? 'status-active' : 'status-inactive'}">${miner.is_active ? 'Активен' : 'Неактивен'}</span></td>
                <td class="action-buttons">
                    <button class="btn-success" onclick="pollMiner(${miner.id})">Опрос</button>
                    <button class="btn-danger" onclick="deleteMiner(${miner.id})">Удалить</button>
                </td>
            `;
            tbody.appendChild(row);
            
            // Добавляем в select для графиков
            const option = document.createElement('option');
            option.value = miner.id;
            option.textContent = `${miner.name} (${miner.ip_address})`;
            chartSelect.appendChild(option);
            
            // Загружаем последние статистики для майнера
            loadLatestStats(miner.id, row);
        });
    } catch (error) {
        console.error('Error loading miners:', error);
    }
}

// Загрузка последних статистик для майнера
async function loadLatestStats(minerId, row) {
    try {
        const response = await fetch(`${API_BASE}/stats/miners/${minerId}?hours=1&limit=1`);
        const stats = await response.json();
        
        if (stats.length > 0) {
            const stat = stats[0];
            const cells = row.querySelectorAll('td');
            // Пропускаем ID, название, производитель/модель, IP, контейнер (0-4), данные начинаются с 5
            cells[5].textContent = formatHashrate(stat.hash_rate);
            cells[6].textContent = stat.temperature ? `${stat.temperature.toFixed(1)}°C` : '-';
            cells[7].textContent = new Date(stat.timestamp).toLocaleString('ru-RU');
        }
    } catch (error) {
        console.error(`Error loading stats for miner ${minerId}:`, error);
    }
}

// Инициализация графика
function initializeChart() {
    const ctx = document.getElementById('stats-chart');
    statsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Значение',
                data: [],
                borderColor: 'rgb(52, 152, 219)',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                tension: 0.1
            }]
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

// Обновление графика
async function updateChart() {
    const minerId = document.getElementById('chart-miner-select').value;
    const metric = document.getElementById('chart-metric').value;
    const hours = parseInt(document.getElementById('chart-hours').value);
    
    if (!minerId) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/stats/miners/${minerId}?hours=${hours}&limit=1000`);
        const stats = await response.json();
        
        if (stats.length === 0) {
            alert('Нет данных для отображения');
            return;
        }
        
        // Сортируем по времени
        stats.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        const labels = stats.map(s => new Date(s.timestamp).toLocaleString('ru-RU'));
        const data = stats.map(s => s[metric] || 0);
        
        let label = '';
        switch(metric) {
            case 'hash_rate':
                label = 'Хешрейт (TH/s)';
                break;
            case 'temperature':
                label = 'Температура (°C)';
                break;
            case 'accepted_shares':
                label = 'Принятые шары';
                break;
            case 'rejected_shares':
                label = 'Отклоненные шары';
                break;
            case 'power_consumption':
                label = 'Потребление энергии (W)';
                break;
        }
        
        statsChart.data.labels = labels;
        statsChart.data.datasets[0].label = label;
        statsChart.data.datasets[0].data = data;
        statsChart.update();
    } catch (error) {
        console.error('Error updating chart:', error);
        alert('Ошибка при загрузке данных для графика');
    }
}

// Добавление контейнера
async function addContainer(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    try {
        const response = await fetch(`${API_BASE}/containers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: formData.get('name'),
                description: formData.get('description'),
                location: formData.get('location')
            })
        });
        
        if (response.ok) {
            closeModal('add-container-modal');
            event.target.reset();
            loadContainers();
            loadOverview();
        } else {
            alert('Ошибка при добавлении контейнера');
        }
    } catch (error) {
        console.error('Error adding container:', error);
        alert('Ошибка при добавлении контейнера');
    }
}

// Загрузка моделей майнеров
async function updateMinerModels() {
    const manufacturerSelect = document.getElementById('miner-manufacturer');
    const modelSelect = document.getElementById('miner-model');
    const manufacturer = manufacturerSelect.value;
    
    if (!manufacturer) {
        modelSelect.innerHTML = '<option value="">Сначала выберите производителя</option>';
        modelSelect.disabled = true;
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/miners/models/${encodeURIComponent(manufacturer)}`);
        const data = await response.json();
        
        modelSelect.innerHTML = '<option value="">Выберите модель</option>';
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });
        modelSelect.disabled = false;
    } catch (error) {
        console.error('Error loading models:', error);
        modelSelect.innerHTML = '<option value="">Ошибка загрузки моделей</option>';
    }
}

// Добавление майнера
async function addMiner(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    try {
        const response = await fetch(`${API_BASE}/miners`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: formData.get('name'),
                manufacturer: formData.get('manufacturer') || null,
                model: formData.get('model') || null,
                ip_address: formData.get('ip_address'),
                port: parseInt(formData.get('port')) || 4028,
                container_id: formData.get('container_id') ? parseInt(formData.get('container_id')) : null,
                is_active: true
            })
        });
        
        if (response.ok) {
            closeModal('add-miner-modal');
            event.target.reset();
            // Сброс полей производителя и модели
            document.getElementById('miner-manufacturer').value = '';
            document.getElementById('miner-model').innerHTML = '<option value="">Сначала выберите производителя</option>';
            document.getElementById('miner-model').disabled = true;
            loadMiners();
            loadOverview();
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка при добавлении майнера: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error adding miner:', error);
        alert('Ошибка при добавлении майнера');
    }
}

// Удаление майнера
async function deleteMiner(minerId) {
    if (!confirm('Вы уверены, что хотите удалить этого майнера?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/miners/${minerId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadMiners();
            loadOverview();
        } else {
            alert('Ошибка при удалении майнера');
        }
    } catch (error) {
        console.error('Error deleting miner:', error);
        alert('Ошибка при удалении майнера');
    }
}

// Опрос майнера
async function pollMiner(minerId) {
    try {
        const response = await fetch(`${API_BASE}/miners/${minerId}/poll`, {
            method: 'POST'
        });
        
        if (response.ok) {
            alert('Майнер успешно опрошен');
            loadMiners();
        } else {
            alert('Ошибка при опросе майнера');
        }
    } catch (error) {
        console.error('Error polling miner:', error);
        alert('Ошибка при опросе майнера');
    }
}

// Модальные окна
function showAddContainerModal() {
    document.getElementById('add-container-modal').style.display = 'block';
}

function showAddMinerModal() {
    document.getElementById('add-miner-modal').style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Обновление данных
function refreshContainers() {
    loadContainers();
    loadOverview();
}

function refreshMiners() {
    loadMiners();
}

function setupContainersList() {
    loadContainers();
}

// Утилиты
function formatHashrate(hashrate) {
    if (!hashrate || hashrate === 0) return '-';
    if (hashrate >= 1000) {
        return `${(hashrate / 1000).toFixed(2)} PH/s`;
    }
    return `${hashrate.toFixed(2)} TH/s`;
}

// Закрытие модальных окон при клике вне их
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}
