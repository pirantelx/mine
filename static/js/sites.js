// ============ SITES ============

// Загрузка списка площадок
async function loadSites() {
    try {
        const response = await fetch(`${API_BASE}/sites`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        if (response.status === 401) {
            logout();
            return;
        }
        const sites = await response.json();
        
        const siteFilter = document.getElementById('site-filter');
        const minerSiteSelect = document.getElementById('miner-site-select');
        const sitesList = document.getElementById('sites-list');
        
        if (siteFilter) {
            siteFilter.innerHTML = '<option value="">Все площадки</option>';
        }
        if (minerSiteSelect) {
            minerSiteSelect.innerHTML = '<option value="">Не выбрана</option>';
        }
        if (sitesList) {
            sitesList.innerHTML = '';
        }
        
        sites.forEach(site => {
            if (siteFilter) {
                const option1 = document.createElement('option');
                option1.value = site.id;
                option1.textContent = site.name;
                siteFilter.appendChild(option1);
            }
            
            if (minerSiteSelect) {
                const option2 = document.createElement('option');
                option2.value = site.id;
                option2.textContent = site.name;
                minerSiteSelect.appendChild(option2);
            }
            
            if (sitesList) {
                const card = document.createElement('div');
                card.className = 'container-card';
                card.innerHTML = `
                    <h3>${site.name}</h3>
                    <p><strong>Контейнеров:</strong> ${site.container_count}</p>
                    <p><strong>Местоположение:</strong> ${site.location || 'Не указано'}</p>
                    <div class="action-buttons">
                        <button onclick="viewSiteContainers(${site.id})">Контейнеры</button>
                        <button class="btn-danger" onclick="deleteSite(${site.id})">Удалить</button>
                    </div>
                `;
                sitesList.appendChild(card);
            }
        });
    } catch (error) {
        console.error('Error loading sites:', error);
    }
}

// Добавление площадки
async function addSite(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    try {
        const response = await fetch(`${API_BASE}/sites`, {
            method: 'POST',
            headers: getAuthHeaders(),
            credentials: 'include',
            body: JSON.stringify({
                name: formData.get('name'),
                description: formData.get('description') || null,
                location: formData.get('location') || null
            })
        });
        
        if (response.ok) {
            closeModal('add-site-modal');
            event.target.reset();
            loadSites();
            loadOverview();
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка при добавлении площадки: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error adding site:', error);
        alert('Ошибка при добавлении площадки');
    }
}

// Удаление площадки
async function deleteSite(siteId) {
    if (!confirm('Вы уверены, что хотите удалить эту площадку? Контейнеры не будут удалены, но связь с площадкой будет разорвана.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/sites/${siteId}`, {
            method: 'DELETE',
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        if (response.status === 401) {
            logout();
            return;
        }
        
        if (response.ok) {
            loadSites();
            loadContainers();
            loadOverview();
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Ошибка: ${errorData.detail || 'Неизвестная ошибка'}`);
        }
    } catch (error) {
        console.error('Error deleting site:', error);
        alert('Ошибка при удалении площадки');
    }
}

function viewSiteContainers(siteId) {
    // Переходим на страницу площадки
    window.location.href = `/sites/${siteId}`;
}

function showAddSiteModal() {
    document.getElementById('add-site-modal').style.display = 'block';
}

function refreshSites() {
    loadSites();
    loadOverview();
}

// Обновление списка контейнеров при выборе площадки
async function updateContainersBySite() {
    const siteId = document.getElementById('miner-site-select').value;
    const containerSelect = document.querySelector('#add-miner-form select[name="container_id"]');
    
    if (!siteId) {
        // Загружаем все контейнеры
        loadContainers();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/containers`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        if (response.ok) {
            const containers = await response.json();
            containerSelect.innerHTML = '<option value="">Не выбран</option>';
            containers
                .filter(c => c.site_id == siteId)
                .forEach(container => {
                    const option = document.createElement('option');
                    option.value = container.id;
                    option.textContent = container.name;
                    containerSelect.appendChild(option);
                });
        }
    } catch (error) {
        console.error('Error loading containers by site:', error);
    }
}

// ============ TAGS ============

// Загрузка всех тегов
async function loadTags() {
    try {
        const response = await fetch(`${API_BASE}/miners/tags`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        if (response.status === 401) {
            logout();
            return;
        }
        const data = await response.json();
        const tagFilter = document.getElementById('tag-filter');
        if (tagFilter) {
            tagFilter.innerHTML = '<option value="">Все теги</option>';
            data.tags.forEach(tag => {
                const option = document.createElement('option');
                option.value = tag;
                option.textContent = tag;
                tagFilter.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading tags:', error);
    }
}

// Редактирование тегов майнера
async function editMinerTags(minerId) {
    try {
        const response = await fetch(`${API_BASE}/miners/${minerId}`, {
            headers: getAuthHeaders(),
            credentials: 'include'
        });
        if (response.ok) {
            const miner = await response.json();
            const currentTags = miner.tags ? miner.tags.join(', ') : '';
            const newTags = prompt('Введите теги через запятую:', currentTags);
            if (newTags !== null) {
                const tagsArray = newTags.split(',').map(t => t.trim()).filter(t => t);
                const updateResponse = await fetch(`${API_BASE}/miners/${minerId}`, {
                    method: 'PUT',
                    headers: getAuthHeaders(),
                    credentials: 'include',
                    body: JSON.stringify({
                        tags: tagsArray
                    })
                });
                if (updateResponse.ok) {
                    loadMiners();
                    loadTags();
                } else {
                    alert('Ошибка при обновлении тегов');
                }
            }
        }
    } catch (error) {
        console.error('Error editing tags:', error);
        alert('Ошибка при редактировании тегов');
    }
}
