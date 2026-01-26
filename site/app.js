// Initialize map centered on Paris
const map = L.map('map').setView([48.8566, 2.3522], 12);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

// Global variables
let geojsonData = null;
let geojsonLayer = null;
const days = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];

// Initialize Day Selector
function initDaySelector() {
    const select = document.getElementById('day-select');
    const todayIndex = new Date().getDay();
    
    // Reorder days to start with Monday (or keep standard week order? Let's use standard Lundi-Dimanche for the list, but handle "Today" logic)
    // Actually, let's list the next 7 days starting from today? Or just the static week days?
    // The user request says: "la sélection par défaut est 'aujourd'hui [jour]'".
    // Let's list standard week days, and mark the current one.
    
    // Standard French week starts Monday
    const weekOrder = [1, 2, 3, 4, 5, 6, 0]; // Mon to Sun
    
    weekOrder.forEach(dayIndex => {
        const dayName = days[dayIndex];
        const option = document.createElement('option');
        option.value = dayName;
        
        if (dayIndex === todayIndex) {
            option.text = `Aujourd'hui (${dayName})`;
            option.selected = true;
        } else {
            option.text = dayName;
        }
        select.appendChild(option);
    });

    select.addEventListener('change', () => {
        updateMap();
    });
}

// Helper to parse time string "HH h MM" to minutes from midnight
function parseTime(timeStr) {
    timeStr = timeStr.replace(/\u00a0/g, ' ').replace(/&nbsp;/g, ' ');
    const parts = timeStr.split('h');
    if (parts.length !== 2) return null;
    const hours = parseInt(parts[0].trim());
    const minutes = parseInt(parts[1].trim());
    return hours * 60 + minutes;
}

// Helper to parse a range string "07 h 00 – 08 h 30"
function parseRange(rangeStr) {
    const parts = rangeStr.split(/[–-]/);
    if (parts.length !== 2) return null;
    const start = parseTime(parts[0].trim());
    const end = parseTime(parts[1].trim());
    if (start === null || end === null) return null;
    return { start, end };
}

// Get status for a specific day
function getPoolStatus(horaires, selectedDay) {
    const now = new Date();
    const currentDayIndex = now.getDay();
    const currentDayName = days[currentDayIndex];
    const isToday = (selectedDay === currentDayName);
    
    const currentMinutes = now.getHours() * 60 + now.getMinutes();
    
    if (!horaires || !horaires[selectedDay]) {
        return { status: 'closed', message: 'Fermé ce jour' };
    }

    const daySchedule = horaires[selectedDay];
    const rangeRegex = /(\d{1,2}\s*h\s*\d{2}\s*[–-]\s*\d{1,2}\s*h\s*\d{2})/g;
    const matches = daySchedule.match(rangeRegex);
    
    if (!matches) {
        // Sometimes it might say "Fermé" or have no ranges
        return { status: 'closed', message: 'Fermé' };
    }

    const ranges = matches.map(parseRange).filter(r => r !== null);
    ranges.sort((a, b) => a.start - b.start);

    // If it's NOT today, we just want to know if it's open at all that day.
    // User request: "bleu pour les pisicines qui vont ouvrir (avec le prochain créneau...)"
    // For future days, "vont ouvrir" means "open that day".
    if (!isToday) {
        if (ranges.length > 0) {
            // Show the first slot or full schedule?
            // Let's show the full schedule in message, or just "Ouvert : ..."
            // For the badge, maybe just the first slot to keep it short.
            const firstRange = ranges[0];
            const startH = Math.floor(firstRange.start / 60);
            const startM = firstRange.start % 60;
            const endH = Math.floor(firstRange.end / 60);
            const endM = firstRange.end % 60;
            const startStr = `${startH}h${startM.toString().padStart(2, '0')}`;
            const endStr = `${endH}h${endM.toString().padStart(2, '0')}`;
            
            return { 
                status: 'opening-soon', // Blue
                message: `Ouvert : ${startStr} - ${endStr}` + (ranges.length > 1 ? ' ...' : '')
            };
        } else {
            return { status: 'closed', message: 'Fermé' };
        }
    }

    // Logic for TODAY
    for (let i = 0; i < ranges.length; i++) {
        const { start, end } = ranges[i];
        
        // Check if open now
        if (currentMinutes >= start && currentMinutes < end) {
            const endH = Math.floor(end / 60);
            const endM = end % 60;
            const endStr = `${endH}h${endM.toString().padStart(2, '0')}`;
            
            // Last entry is 45 mins before closing
            const lastEntryMinutes = end - 45;
            const lastEntryH = Math.floor(lastEntryMinutes / 60);
            const lastEntryM = lastEntryMinutes % 60;
            const lastEntryStr = `${lastEntryH}h${lastEntryM.toString().padStart(2, '0')}`;

            // Check if closing soon (within 45 mins of closing)
            if (currentMinutes >= lastEntryMinutes) {
                 return { 
                     status: 'closing-soon', // Orange
                     message: `Ferme à ${endStr}`,
                     lastEntry: `Dernier accès : ${lastEntryStr}`
                 };
            }

            return { 
                status: 'open', 
                message: `Ferme à ${endStr}`,
                lastEntry: `Dernier accès : ${lastEntryStr}`
            };
        }
        
        // Check if opening soon
        if (currentMinutes < start) {
            const startH = Math.floor(start / 60);
            const startM = start % 60;
            const endH = Math.floor(end / 60);
            const endM = end % 60;
            const startStr = `${startH}h${startM.toString().padStart(2, '0')}`;
            const endStr = `${endH}h${endM.toString().padStart(2, '0')}`;
            return { status: 'opening-soon', message: `Ouvre à ${startStr} (${startStr} - ${endStr})` };
        }
    }

    return { status: 'closed', message: 'Fermé pour la journée' };
}

// Create custom icon
function createCustomIcon(status) {
    let cssClass = 'marker-pin';
    if (status === 'open') cssClass += ' open';
    else if (status === 'opening-soon') cssClass += ' opening-soon';
    else if (status === 'closing-soon') cssClass += ' closing-soon';
    else cssClass += ' closed';

    return L.divIcon({
        className: 'custom-marker',
        html: `<div class="${cssClass}"></div>`,
        iconSize: [30, 42],
        iconAnchor: [15, 42]
    });
}

// Drawer Logic
const drawer = document.getElementById('drawer');
const drawerContent = document.getElementById('drawer-content');
const drawerClose = document.getElementById('drawer-close');

drawerClose.addEventListener('click', closeDrawer);

function openDrawer(props, statusInfo, selectedDay) {
    let bassinsHtml = '';
    if (props.bassins && props.bassins.length > 0) {
        bassinsHtml = '<ul class="bassins-list">';
        props.bassins.forEach(b => {
            bassinsHtml += `<li>${b}</li>`;
        });
        bassinsHtml += '</ul>';
    }

    let scheduleHtml = '';
    if (props.horaires && props.horaires[selectedDay]) {
        scheduleHtml = `<p><strong>Horaires (${selectedDay}):</strong><br>${props.horaires[selectedDay]}</p>`;
    }

    let statusBadgeClass = 'status-closed';
    if (statusInfo.status === 'open') statusBadgeClass = 'status-open';
    else if (statusInfo.status === 'opening-soon') statusBadgeClass = 'status-soon';
    else if (statusInfo.status === 'closing-soon') statusBadgeClass = 'status-closing-soon';

    const content = `
        <h2>${props.nom}</h2>
        <div class="status-badge ${statusBadgeClass}">${statusInfo.message}</div>
        ${statusInfo.lastEntry ? `<p style="color: #d35400; font-weight: bold; font-size: 13px;">⚠️ ${statusInfo.lastEntry}</p>` : ''}
        <p><strong>Adresse:</strong> <a href="https://cartes.app/?q=${encodeURIComponent(props.adresse)}" target="_blank">${props.adresse}</a></p>
        ${scheduleHtml}
        <p><a href="${props.url}" target="_blank">Voir sur paris.fr</a></p>
        ${bassinsHtml ? `<p><strong>Bassins:</strong></p>${bassinsHtml}` : ''}
    `;

    drawerContent.innerHTML = content;
    drawer.classList.add('open');
}

function closeDrawer() {
    drawer.classList.remove('open');
}

// Map click to close drawer
map.on('click', () => {
    closeDrawer();
});

function updateMap() {
    if (!geojsonData) return;
    
    if (geojsonLayer) {
        map.removeLayer(geojsonLayer);
    }

    const selectedDay = document.getElementById('day-select').value;

    geojsonLayer = L.geoJSON(geojsonData, {
        pointToLayer: function(feature, latlng) {
            const statusInfo = getPoolStatus(feature.properties.horaires, selectedDay);
            return L.marker(latlng, { icon: createCustomIcon(statusInfo.status) });
        },
        onEachFeature: function(feature, layer) {
            const props = feature.properties;
            
            layer.on('click', (e) => {
                L.DomEvent.stopPropagation(e); // Prevent map click
                const statusInfo = getPoolStatus(props.horaires, selectedDay);
                openDrawer(props, statusInfo, selectedDay);
                
                // Center map on marker (optional, but nice on mobile)
                map.panTo(e.latlng);
            });
        }
    }).addTo(map);
}

// Load GeoJSON
fetch('piscines_paris.geojson')
    .then(response => response.json())
    .then(data => {
        geojsonData = data;
        initDaySelector();
        updateMap();
    })
    .catch(error => console.error('Error loading GeoJSON:', error));
