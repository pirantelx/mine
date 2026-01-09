let statsChart = null;
const API_BASE = '/api';

// Обертка для fetch с автоматической отправкой cookies
async function apiFetch(url, options = {}) {
    const defaultOptions = {
        credentials: 'include',  // Всегда отправляем cookies
        ...options
    };
    // Добавляем headers, если они есть
    if (options.headers) {
        defaultOptions.headers = {
            ...options.headers
        };
    }
    return fetch(url, defaultOptions);
}

// Проверка авторизации
function checkAuth() {
    // Проверяем токен в localStorage или cookie
    let token = localStorage.getItem('access_token');
    
    if (!token) {
        // Пытаемся получить из cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'access_token') {
                token = value;
                // Сохраняем в localStorage для удобства
                localStorage.setItem('access_token', token);
                break;
            }
        }
    }
    
    if (!token) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

// Функция для добавления токена к запросам
function getAuthHeaders() {
    // Сначала пытаемся получить токен из localStorage
    let token = localStorage.getItem('access_token');
    
    // Если нет в localStorage, пытаемся получить из cookie
    if (!token) {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'access_token') {
                token = value;
                // Сохраняем в localStorage для удобства
                localStorage.setItem('access_token', token);
                break;
            }
        }
    }
    
    if (!token) {
        console.warn('No access token found, redirecting to login');
        window.location.href = '/login';
        return {};
    }
    
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    if (!checkAuth()) return;
    
    loadUserInfo();
    loadOverview();
    loadSites();
    loadContainers();
    loadPools();
    loadTags();
    loadMiners();
    initializeChart();
    setupContainersList();
});

// Загрузка информации о пользователе
async function loadUserInfo() {
    try {
        const response = await apiFetch(`${API_BASE}/auth/me`, {
            headers: getAuthHeaders()
        });
        
        if (response.ok) {
            const user = await response.json();
            // Отображаем информацию о пользователе
            const userInfo = document.getElementById('user-info');
            if (userInfo) {
                userInfo.textContent = `${user.username} (${user.role})`;
            }
            
            // Показываем кнопки только для администраторов
            if (user.role === 'admin') {
                const scanBtn = document.getElementById('scan-network-btn');
                if (scanBtn) scanBtn.style.display = 'inline-block';
                const addSiteBtn = document.getElementById('add-site-btn');
                if (addSiteBtn) addSiteBtn.style.display = 'inline-block';
            }
            
            console.log('Logged in as:', user.username, 'Role:', user.role);
        } else if (response.status === 401) {
            // Токен недействителен
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
    } catch (error) {
        console.error('Error loading user info:', error);
    }
}

// Выход
async function logout() {
    try {
        // Вызываем API для удаления cookie на сервере
        await fetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            credentials: 'include'  // Важно для отправки cookies
        });
    } catch (error) {
        console.error('Error during logout:', error);
    }
    
    // Удаляем токен из localStorage
    localStorage.removeItem('access_token');
    // Перенаправляем на страницу входа
    window.location.href = '/login';
}

// Загрузка общей статистики
async function loadOverview() {
    try {
        const headers = getAuthHeaders();
        if (Object.keys(headers).length === 0) {
            return; // Уже перенаправлено на логин
        }
        
        const containersResponse = await fetch(`${API_BASE}/containers`, {
            headers: headers
        });
        if (containersResponse.status === 401) {
            logout();
            return;
        }
        const containers = await containersResponse.json();
        
        const minersResponse = await fetch(`${API_BASE}/miners`, {
            headers: headers
        });
        if (minersResponse.status === 401) {
            logout();
            return;
        }
        const miners = await minersResponse.json();
        
        const overviewResponse = await fetch(`${API_BASE}/stats/overview`, {
            headers: headers
        });
        if (overviewResponse.status === 401) {
            logout();
            return;
        }
        const overview = await overviewResponse.json();
        
        document.getElementById('total-containers').textContent = containers.length;
        document.getElementById('total-miners').textContent = miners.length;
        document.getElementById('active-miners').textContent = miners.filter(m => m.is_active).length;
        
        const totalHashrate = overview.reduce((sum, c) => sum + (c.total_hash_rate || 0), 0);
        document.getElementById('total-hashrate').textContent = formatHashrate(totalHashrate);
        
        // Загружаем количество пулов и площадок
        try {
            const poolsResponse = await fetch(`${API_BASE}/pools`, { headers: getAuthHeaders() });
            if (poolsResponse.ok) {
                const pools = await poolsResponse.json();
                document.getElementById('total-pools').textContent = pools.length || 0;
            }
            const sitesResponse = await fetch(`${API_BASE}/sites`, { headers: getAuthHeaders() });
            if (sitesResponse.ok) {
                const sites = await sitesResponse.json();
                document.getElementById('total-sites').textContent = sites.length || 0;
            }
        } catch (e) {
            console.error('Error loading counts:', e);
        }
    } catch (error) {
        console.error('Error loading overview:', error);
    }
}

// Загрузка списка контейнеров
async function loadContainers() {
    try {
        const response = await fetch(`${API_BASE}/containers`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
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
        const poolId = document.getElementById('pool-filter').value;
        let url = `${API_BASE}/miners`;
        const params = [];
        if (containerId) {
            params.push(`container_id=${containerId}`);
        }
        if (poolId) {
            params.push(`pool_id=${poolId}`);
        }
        if (params.length > 0) {
            url += '?' + params.join('&');
        }
        
        const response = await fetch(url, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
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
            const tagsDisplay = miner.tags && miner.tags.length > 0 
                ? miner.tags.map(t => `<span class="tag-badge">${t}</span>`).join(' ')
                : '-';
            row.innerHTML = `
                <td>${miner.id}</td>
                <td>${miner.name}${miner.is_auto_discovered ? ' <span style="color: #3498db; font-size: 0.8em;">(авто)</span>' : ''}</td>
                <td>${manufacturerModel}</td>
                <td>${miner.ip_address}:${miner.port}</td>
                <td>${miner.container_name || '-'}</td>
                <td>${miner.pool_name || '-'}</td>
                <td>${tagsDisplay}</td>
                <td>-</td>
                <td>-</td>
                <td>${miner.last_seen ? new Date(miner.last_seen).toLocaleString('ru-RU') : 'Никогда'}</td>
                <td><span class="status-badge ${miner.is_active ? 'status-active' : 'status-inactive'}">${miner.is_active ? 'Активен' : 'Неактивен'}</span></td>
                <td class="action-buttons">
                    <button class="btn-success" onclick="pollMiner(${miner.id})">Опрос</button>
                    <button onclick="editMinerTags(${miner.id})">Теги</button>
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
        const response = await fetch(`${API_BASE}/stats/miners/${minerId}?hours=1&limit=1`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        const stats = await response.json();
        
        if (stats.length > 0) {
            const stat = stats[0];
            const cells = row.querySelectorAll('td');
            // Пропускаем ID, название, производитель/модель, IP, контейнер, пул, теги (0-6), данные начинаются с 7
            cells[7].textContent = formatHashrate(stat.hash_rate);
            cells[8].textContent = stat.temperature ? `${stat.temperature.toFixed(1)}°C` : '-';
            cells[9].textContent = new Date(stat.timestamp).toLocaleString('ru-RU');
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
        const response = await fetch(`${API_BASE}/stats/miners/${minerId}?hours=${hours}&limit=1000`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
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
            headers: getAuthHeaders(),
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
        const response = await fetch(`${API_BASE}/miners/models/${encodeURIComponent(manufacturer)}`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
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
            headers: getAuthHeaders(),
            body: JSON.stringify({
                name: formData.get('name'),
                manufacturer: formData.get('manufacturer') || null,
                model: formData.get('model') || null,
                ip_address: formData.get('ip_address'),
                port: parseInt(formData.get('port')) || 4028,
                container_id: formData.get('container_id') ? parseInt(formData.get('container_id')) : null,
                pool_id: formData.get('pool_id') ? parseInt(formData.get('pool_id')) : null,
                tags: formData.get('tags') ? formData.get('tags').split(',').map(t => t.trim()).filter(t => t) : null,
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
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        
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
            method: 'POST',
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        
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

// ============ POOLS ============

// Загрузка списка пулов
async function loadPools() {
    try {
        const response = await fetch(`${API_BASE}/pools`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        const pools = await response.json();
        
        const poolFilter = document.getElementById('pool-filter');
        const addMinerPoolSelect = document.querySelector('#add-miner-form select[name="pool_id"]');
        const addToPoolSelect = document.getElementById('add-to-pool-select');
        const poolsList = document.getElementById('pools-list');
        
        // Очищаем select'ы
        if (poolFilter) {
            poolFilter.innerHTML = '<option value="">Все пулы</option>';
        }
        if (addMinerPoolSelect) {
            addMinerPoolSelect.innerHTML = '<option value="">Не выбран</option>';
        }
        if (addToPoolSelect) {
            addToPoolSelect.innerHTML = '<option value="">Не добавлять в пул</option>';
        }
        if (poolsList) {
            poolsList.innerHTML = '';
        }
        
        pools.forEach(pool => {
            // Добавляем в фильтр
            if (poolFilter) {
                const option1 = document.createElement('option');
                option1.value = pool.id;
                option1.textContent = pool.name;
                poolFilter.appendChild(option1);
            }
            
            // Добавляем в форму добавления майнера
            if (addMinerPoolSelect) {
                const option2 = document.createElement('option');
                option2.value = pool.id;
                option2.textContent = pool.name;
                addMinerPoolSelect.appendChild(option2);
            }
            
            // Добавляем в форму добавления найденных майнеров
            if (addToPoolSelect) {
                const option3 = document.createElement('option');
                option3.value = pool.id;
                option3.textContent = pool.name;
                addToPoolSelect.appendChild(option3);
            }
            
            // Добавляем в список пулов
            if (poolsList) {
                const card = document.createElement('div');
                card.className = 'container-card';
                card.innerHTML = `
                    <h3>${pool.name}</h3>
                    <p><strong>Майнеров:</strong> ${pool.miner_count}</p>
                    <p><strong>Описание:</strong> ${pool.description || 'Нет описания'}</p>
                    <div class="action-buttons">
                        <button onclick="viewPoolStats(${pool.id})">Статистика</button>
                        <button class="btn-danger" onclick="deletePool(${pool.id})">Удалить</button>
                    </div>
                `;
                poolsList.appendChild(card);
            }
        });
    } catch (error) {
        console.error('Error loading pools:', error);
    }
}

// Добавление пула
async function addPool(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    try {
        const response = await fetch(`${API_BASE}/pools`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                name: formData.get('name'),
                description: formData.get('description') || null
            })
        });
        
        if (response.ok) {
            closeModal('add-pool-modal');
            event.target.reset();
            loadPools();
            loadOverview();
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка при добавлении пула: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error adding pool:', error);
        alert('Ошибка при добавлении пула');
    }
}

// Удаление пула
async function deletePool(poolId) {
    if (!confirm('Вы уверены, что хотите удалить этот пул? Майнеры не будут удалены, но связь с пулом будет разорвана.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/pools/${poolId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        
        if (response.ok) {
            loadPools();
            loadMiners();
            loadOverview();
        } else {
            alert('Ошибка при удалении пула');
        }
    } catch (error) {
        console.error('Error deleting pool:', error);
        alert('Ошибка при удалении пула');
    }
}

// Просмотр статистики пула
async function viewPoolStats(poolId) {
    try {
        const response = await fetch(`${API_BASE}/stats/pools/${poolId}?hours=24`, {
            headers: getAuthHeaders()
        });
        if (response.status === 401) {
            logout();
            return;
        }
        const stats = await response.json();
        alert(`Статистика пула:\n\n` +
              `Всего майнеров: ${stats.total_miners}\n` +
              `Активных: ${stats.active_miners}\n` +
              `Общий хешрейт: ${stats.total_hash_rate ? formatHashrate(stats.total_hash_rate) : 'Нет данных'}\n` +
              `Средняя температура: ${stats.avg_temperature ? stats.avg_temperature.toFixed(1) + '°C' : 'Нет данных'}\n` +
              `Среднее потребление: ${stats.avg_power_consumption ? stats.avg_power_consumption.toFixed(2) + 'W' : 'Нет данных'}`);
    } catch (error) {
        console.error('Error loading pool stats:', error);
        alert('Ошибка при загрузке статистики пула');
    }
}

function showAddPoolModal() {
    document.getElementById('add-pool-modal').style.display = 'block';
}

function showPoolsSection() {
    document.querySelector('.miners-section').style.display = 'none';
    document.querySelector('.containers-section').style.display = 'none';
    document.querySelector('.charts-section').style.display = 'none';
    document.getElementById('pools-section').style.display = 'block';
    loadPools();
}

// ============ NETWORK SCANNING ============

let discoveredMiners = [];

function showScanNetworkModal() {
    document.getElementById('scan-network-modal').style.display = 'block';
    document.getElementById('scan-results').style.display = 'none';
    discoveredMiners = [];
}

async function scanNetwork(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    const scanButton = event.target.querySelector('button[type="submit"]');
    scanButton.disabled = true;
    scanButton.textContent = 'Сканирование...';
    
    try {
        const response = await fetch(`${API_BASE}/network/scan`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                network: formData.get('network'),
                port: parseInt(formData.get('port')) || 4028,
                timeout: parseFloat(formData.get('timeout')) || 2.0
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            discoveredMiners = data.discovered_miners || [];
            displayDiscoveredMiners();
            document.getElementById('scan-results').style.display = 'block';
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка при сканировании: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error scanning network:', error);
        alert('Ошибка при сканировании сети');
    } finally {
        scanButton.disabled = false;
        scanButton.textContent = 'Сканировать';
    }
}

function displayDiscoveredMiners() {
    const list = document.getElementById('discovered-miners-list');
    list.innerHTML = '';
    
    if (discoveredMiners.length === 0) {
        list.innerHTML = '<p>Майнеры не найдены</p>';
        return;
    }
    
    const table = document.createElement('table');
    table.className = 'miners-table';
    table.innerHTML = `
        <thead>
            <tr>
                <th><input type="checkbox" id="select-all-miners" onchange="toggleAllMiners(this.checked)"></th>
                <th>IP адрес</th>
                <th>Порт</th>
                <th>Производитель</th>
                <th>Модель</th>
                <th>Статус</th>
            </tr>
        </thead>
        <tbody>
            ${discoveredMiners.map((miner, index) => `
                <tr>
                    <td><input type="checkbox" class="miner-checkbox" value="${index}" ${miner.is_accessible ? '' : 'disabled'}></td>
                    <td>${miner.ip_address}</td>
                    <td>${miner.port}</td>
                    <td>${miner.manufacturer || 'Не определен'}</td>
                    <td>${miner.model || '-'}</td>
                    <td>${miner.is_accessible ? '<span class="status-badge status-active">Доступен</span>' : '<span class="status-badge status-inactive">Недоступен</span>'}</td>
                </tr>
            `).join('')}
        </tbody>
    `;
    list.appendChild(table);
}

function toggleAllMiners(checked) {
    document.querySelectorAll('.miner-checkbox').forEach(cb => {
        if (!cb.disabled) {
            cb.checked = checked;
        }
    });
}

async function addDiscoveredMiners() {
    const selected = Array.from(document.querySelectorAll('.miner-checkbox:checked'))
        .map(cb => discoveredMiners[parseInt(cb.value)])
        .filter(m => m.is_accessible);
    
    if (selected.length === 0) {
        alert('Выберите хотя бы один доступный майнер');
        return;
    }
    
    const poolId = document.getElementById('add-to-pool-select').value;
    const containerId = document.getElementById('add-to-container-select').value;
    
    try {
        const response = await fetch(`${API_BASE}/network/discovered/add?${poolId ? `pool_id=${poolId}&` : ''}${containerId ? `container_id=${containerId}` : ''}`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(selected)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`Добавлено майнеров: ${result.added}\nПропущено: ${result.skipped}`);
            closeModal('scan-network-modal');
            loadMiners();
            loadOverview();
            loadPools();
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка при добавлении: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error adding discovered miners:', error);
        alert('Ошибка при добавлении майнеров');
    }
}
