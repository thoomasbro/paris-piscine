// Initialize map centered on Paris
const map = L.map('map').setView([48.8566, 2.3522], 12);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

// Helper to parse time string "HH h MM" to minutes from midnight
function parseTime(timeStr) {
    // Expected format: "07 h 00" or "22 h 30"
    // Remove non-breaking spaces if any
    timeStr = timeStr.replace(/\u00a0/g, ' ').replace(/&nbsp;/g, ' ');
    const parts = timeStr.split('h');
    if (parts.length !== 2) return null;
    const hours = parseInt(parts[0].trim());
    const minutes = parseInt(parts[1].trim());
    return hours * 60 + minutes;
}

// Helper to parse a range string "07 h 00 – 08 h 30"
function parseRange(rangeStr) {
    // Split by en-dash or hyphen
    const parts = rangeStr.split(/[–-]/);
    if (parts.length !== 2) return null;
    const start = parseTime(parts[0].trim());
    const end = parseTime(parts[1].trim());
    if (start === null || end === null) return null;
    return { start, end };
}

// Get current status
function getPoolStatus(horaires) {
    const now = new Date();
    const days = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];
    const currentDayName = days[now.getDay()];
    
    const currentMinutes = now.getHours() * 60 + now.getMinutes();
    
    if (!horaires || !horaires[currentDayName]) {
        return { status: 'closed', message: 'Fermé aujourd\'hui' };
    }

    const daySchedule = horaires[currentDayName];
    // Example schedule: "07 h 00 – 08 h 30 11 h 30 – 13 h 30"
    // We need to split multiple ranges. They are usually separated by spaces or newlines in the raw text, 
    // but in our JSON they might be concatenated.
    // Based on our scraper, it seems they are just concatenated with spaces.
    // Regex to find patterns like "DD h DD – DD h DD"
    const rangeRegex = /(\d{1,2}\s*h\s*\d{2}\s*[–-]\s*\d{1,2}\s*h\s*\d{2})/g;
    const matches = daySchedule.match(rangeRegex);
    
    if (!matches) {
        return { status: 'closed', message: 'Horaires non reconnus' };
    }

    const ranges = matches.map(parseRange).filter(r => r !== null);
    
    // Sort ranges by start time
    ranges.sort((a, b) => a.start - b.start);

    for (let i = 0; i < ranges.length; i++) {
        const { start, end } = ranges[i];
        
        // Check if open now
        if (currentMinutes >= start && currentMinutes < end) {
            const endH = Math.floor(end / 60);
            const endM = end % 60;
            const endStr = `${endH}h${endM.toString().padStart(2, '0')}`;
            return { status: 'open', message: `Ferme à ${endStr}` };
        }
        
        // Check if opening soon (e.g. next slot is today and we are before it)
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
    else cssClass += ' closed';

    return L.divIcon({
        className: 'custom-marker',
        html: `<div class="${cssClass}"></div>`,
        iconSize: [30, 42],
        iconAnchor: [15, 42]
    });
}

// Load GeoJSON
fetch('piscines_paris.geojson')
    .then(response => response.json())
    .then(data => {
        L.geoJSON(data, {
            pointToLayer: function(feature, latlng) {
                const statusInfo = getPoolStatus(feature.properties.horaires);
                return L.marker(latlng, { icon: createCustomIcon(statusInfo.status) });
            },
            onEachFeature: function(feature, layer) {
                const props = feature.properties;
                const statusInfo = getPoolStatus(props.horaires);
                
                let statusBadgeClass = 'status-closed';
                if (statusInfo.status === 'open') statusBadgeClass = 'status-open';
                else if (statusInfo.status === 'opening-soon') statusBadgeClass = 'status-soon';

                let bassinsHtml = '';
                if (props.bassins && props.bassins.length > 0) {
                    bassinsHtml = '<ul class="bassins-list">';
                    // Limit to first 3 characteristics to avoid huge popups
                    props.bassins.slice(0, 5).forEach(b => {
                        bassinsHtml += `<li>${b}</li>`;
                    });
                    if (props.bassins.length > 5) bassinsHtml += '<li>...</li>';
                    bassinsHtml += '</ul>';
                }

                const popupContent = `
                    <h3>${props.nom}</h3>
                    <div class="status-badge ${statusBadgeClass}">${statusInfo.message}</div>
                    <p><strong>Adresse:</strong> ${props.adresse}</p>
                    <p><a href="${props.url}" target="_blank">Voir sur paris.fr</a></p>
                    ${bassinsHtml ? `<p><strong>Bassins:</strong></p>${bassinsHtml}` : ''}
                `;
                layer.bindPopup(popupContent);
            }
        }).addTo(map);
    })
    .catch(error => console.error('Error loading GeoJSON:', error));
