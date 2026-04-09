// frontend/js/areas.js
window.map = null;
window.marker = null;
window.autocomplete = null;
window.geocoder = null;
window.radiusCircle = null;

// 2. The HTML script tag calls this, but we tell it to wait!
window.initMap = function () {
    console.log("Google Maps API loaded successfully. Waiting for modal to open...");
};

// 3. The On-Demand Map Builder
function buildMapNow() {
    // This strict selector guarantees we ignore any old hidden modals!
    const mapDiv = document.querySelector('#form-area #area-map');

    if (!mapDiv) {
        console.error("CRITICAL: Cannot find the #area-map inside #form-area!");
        return;
    }

    // Ensure the div has explicit height so the map doesn't collapse
    mapDiv.style.height = "350px";
    mapDiv.style.display = "block";

    // If the map already exists, just resize it
    if (window.map) {
        console.log("Resizing existing map...");
        google.maps.event.trigger(window.map, 'resize');
        window.map.setCenter(window.map.getCenter() || { lat: 21.1702, lng: 72.8311 });
        return;
    }

    console.log("Building map for the first time...");

    // Initialize Map with Map ID (required for Advanced Markers)
    window.map = new google.maps.Map(mapDiv, {
        center: { lat: 21.1702, lng: 72.8311 }, // Default to Surat
        zoom: 12,
        mapId: 'DEMO_MAP_ID', // Required for AdvancedMarkerElement
        mapTypeId: 'roadmap'
    });

    // Initialize Advanced Marker
    window.marker = new google.maps.marker.AdvancedMarkerElement({
        map: window.map,
        position: { lat: 21.1702, lng: 72.8311 }, // Default to Surat
        gmpDraggable: true
    });

    // Initialize Radius Circle
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const circleColor = isDark ? '#60a5fa' : '#4f46e5';

    window.radiusCircle = new google.maps.Circle({
        map: window.map,
        center: { lat: 21.1702, lng: 72.8311 },
        radius: parseInt(document.getElementById('a-radius')?.value || 500),
        fillColor: circleColor,
        fillOpacity: isDark ? 0.2 : 0.15,
        strokeColor: circleColor,
        strokeOpacity: 0.8,
        strokeWeight: 2,
        clickable: false
    });

    window.updateRadiusCircle = function (radius) {
        if (window.radiusCircle) {
            window.radiusCircle.setRadius(parseInt(radius));
        }
    };

    // Initialize Services
    window.geocoder = new google.maps.Geocoder();


    // Initialize PlaceAutocompleteElement (Autocomplete is deprecated for new customers as of March 2025)
    // Initialize standard Autocomplete (Keeps Bootstrap styling and works perfectly)
    const input = document.getElementById("map-search");
    if (input) {
        window.autocomplete = new google.maps.places.Autocomplete(input);
        window.autocomplete.bindTo("bounds", window.map);

        window.autocomplete.addListener("place_changed", () => {
            const place = window.autocomplete.getPlace();

            // If the user presses enter without selecting a valid dropdown item
            if (!place.geometry || !place.geometry.location) {
                console.error("No geometry details available for this place.");
                return;
            }

            // Move the Map and Pin
            window.map.setCenter(place.geometry.location);
            window.map.setZoom(15);
            window.marker.position = place.geometry.location;
            if (window.radiusCircle) {
                window.radiusCircle.setCenter(place.geometry.location);
            }

            // Update hidden coordinate fields
            document.getElementById('a-lat').value = place.geometry.location.lat();
            document.getElementById('a-lng').value = place.geometry.location.lng();

            // Auto-fill the Area Name input box if it is currently empty
            const nameInput = document.getElementById('a-name');
            if (nameInput && nameInput.value.trim() === '') {
                nameInput.value = place.name || '';
            }
        });
    }


    // Helper function to get the name of the dropped pin via Reverse Geocoding
    function getNeighborhoodName(latLng) {
        window.geocoder.geocode({ location: latLng }, (results, status) => {
            if (status === "OK" && results[0]) {

                // 1. ALWAYS update the "Search Location on Map" box with the full address
                const searchInput = document.getElementById('map-search');
                if (searchInput) {
                    searchInput.value = results[0].formatted_address;
                }

                // 2. ONLY update the "Area Name" if the user hasn't typed anything yet
                const nameInput = document.getElementById('a-name');
                if (nameInput && nameInput.value.trim() === '') {
                    let areaName = results[0].formatted_address; // Fallback

                    // Hunt for the specific neighborhood name
                    for (let i = 0; i < results.length; i++) {
                        if (results[i].types.includes('sublocality') || results[i].types.includes('locality')) {
                            areaName = results[i].address_components[0].long_name;
                            break;
                        }
                    }
                    nameInput.value = areaName;
                }
            }
        });
    }

    // Map Click Listener
    window.map.addListener('click', (e) => {
        window.marker.position = e.latLng;
        if (window.radiusCircle) window.radiusCircle.setCenter(e.latLng);
        document.getElementById('a-lat').value = e.latLng.lat();
        document.getElementById('a-lng').value = e.latLng.lng();

        // Ask Google for the name of where we just clicked
        getNeighborhoodName(e.latLng);
    });

    // Marker Drag Listener
    window.marker.addListener('dragend', () => {
        const pos = window.marker.position;
        if (window.radiusCircle) window.radiusCircle.setCenter(pos);
        document.getElementById('a-lat').value = pos.lat;
        document.getElementById('a-lng').value = pos.lng;

        // Ask Google for the name of where we just dragged the pin
        getNeighborhoodName(pos);
    });
}

// 4. Attach to Bootstrap's "I am completely finished opening" event
document.addEventListener('DOMContentLoaded', function () {
    const addModalEl = document.getElementById('addModal');
    if (addModalEl) {
        addModalEl.addEventListener('shown.bs.modal', function () {
            // Check if the "New Area" form is the one currently visible
            if (document.getElementById('form-area').style.display !== 'none') {
                buildMapNow();
            }
        });
    }
});

// =========================================================================
// STEP 1 & 2 LOGIC: Handling the Save Area & Discover Shops flow
// =========================================================================

// ── Edit Mode Map Loader ────────────────────────────────────────────────────
// Centers the map and marker on an existing area's saved coordinates.
window.loadMapForEdit = function (lat, lng) {
    // If map was never built (e.g. modal opened directly in edit mode), build it first
    if (!window.map) {
        buildMapNow();
    }
    const latLng = { lat: parseFloat(lat), lng: parseFloat(lng) };
    window.map.setCenter(latLng);
    window.map.setZoom(15);
    if (window.marker) {
        window.marker.position = latLng;
    }
    if (window.radiusCircle) {
        window.radiusCircle.setCenter(latLng);
        window.radiusCircle.setRadius(parseInt(document.getElementById('a-radius')?.value || 500));
    }
    // Trigger a resize in case the map div was hidden
    setTimeout(() => google.maps.event.trigger(window.map, 'resize'), 100);
};


window.handleModalSave = async function () {
    const name = document.getElementById('a-name').value.trim();
    const desc = document.getElementById('a-desc').value.trim();
    const lat = document.getElementById('a-lat').value;
    const lng = document.getElementById('a-lng').value;

    // Advanced Targeting Fields
    const radiusMeters = parseInt(document.getElementById('a-radius').value);
    const shopLimit = parseInt(document.getElementById('a-shop-limit').value);
    const priorityLevel = document.getElementById('a-priority').value;
    const autoDiscoveryEnabled = document.getElementById('a-auto-discovery').checked;
    const targetCategories = Array.from(document.querySelectorAll('.tgt-category:checked')).map(cb => cb.value);

    const existingId = document.getElementById('a-id').value; // non-empty only in edit mode
    const btn = document.getElementById('modal-save-btn');

    const rules = {
        'a-name': 'Area name is required',
        'map-search': () => (lat && lng) ? true : 'Please select a location on the map'
    };

    if (!validateForm(document.getElementById('form-area'), rules)) {
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Synchronizing...';

    try {
        let savedArea;
        const payload = {
            name: name,
            description: desc,
            lat: parseFloat(lat),
            lng: parseFloat(lng),
            radius_meters: radiusMeters,
            shop_limit: shopLimit,
            priority_level: priorityLevel,
            auto_discovery_enabled: autoDiscoveryEnabled,
            target_categories: targetCategories
        };

        if (existingId) {
            // ── Edit Mode: update the existing record ──
            savedArea = await ApiClient.updateArea(existingId, payload);
        } else {
            // ── Create Mode: make a new area ──
            savedArea = await ApiClient.createArea(payload);
        }

        // ── Transition to Step 2: Discovered Shops ──
        document.getElementById('area-step-1').style.display = 'none';
        document.getElementById('discovered-shops-container').style.display = 'block';
        document.getElementById('area-saved-msg').textContent =
            existingId ? `Area "${savedArea.name}" updated!` : `Area "${savedArea.name}" saved!`;

        // Hide the save button — user is now in discovery mode
        btn.style.display = 'none';

        const savedAreaId = savedArea.id || savedArea.data?.id;

        // Only run auto-discovery if the user toggled it on
        if (autoDiscoveryEnabled) {
            window._discoverShops(savedAreaId, { lat: parseFloat(lat), lng: parseFloat(lng) }, radiusMeters, shopLimit, targetCategories);
        } else {
            // If disabled, just close the modal and refresh
            bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
        }

        // Refresh the sidebar list in the background
        if (typeof loadAll === 'function') loadAll();

    } catch (error) {
        console.error("Failed to save area:", error);
        alert(error?.data?.detail || "Failed to save the area.");
        btn.disabled = false;
        btn.textContent = existingId ? 'Update Area' : 'Create Area';
    }
};

window._discoverShops = async function (areaId, locationParams, radiusMeters = 500, maxResults = 20, categories = []) {
    const tableBody = document.getElementById('discovered-shops-table');

    // Show a loading indicator while fetching
    tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-muted"><span class="spinner-border spinner-border-sm text-primary me-2"></span>Scanning for businesses within ${radiusMeters}m...</td></tr>`;

    try {
        // Use legacy PlacesService.nearbySearch — works with standard Maps API keys
        if (!window.map) throw new Error('Map not initialized');

        const service = new google.maps.places.PlacesService(window.map);

        const results = await new Promise((resolve, reject) => {
            service.nearbySearch({
                location: locationParams,
                radius: radiusMeters,
                type: 'store'
            }, (results, status) => {
                if (status === google.maps.places.PlacesServiceStatus.OK && results) {
                    resolve(results);
                } else if (status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
                    resolve([]);
                } else {
                    reject(new Error(`Places API: ${status}`));
                }
            });
        });

        if (!results || results.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-muted">No businesses found within ${radiusMeters}m.</td></tr>`;
            return;
        }

        tableBody.innerHTML = ''; // Clear loading indicator

        // Display results up to maxResults limit
        results.slice(0, maxResults).forEach(place => {
            const row = document.createElement('tr');

            const nameCell = document.createElement('td');
            nameCell.className = 'fw-bold';
            nameCell.textContent = place.name || 'Unnamed Shop';

            const addressCell = document.createElement('td');
            addressCell.textContent = place.vicinity || '—';

            const actionCell = document.createElement('td');
            actionCell.className = 'text-end';

            const addBtn = document.createElement('button');
            addBtn.className = 'btn btn-sm btn-outline-primary fw-semibold';
            addBtn.textContent = 'Add to SRM';
            addBtn.onclick = () => window._addLegacyShop(addBtn, place, areaId);

            actionCell.appendChild(addBtn);
            row.appendChild(nameCell);
            row.appendChild(addressCell);
            row.appendChild(actionCell);
            tableBody.appendChild(row);
        });
    } catch (error) {
        console.error("Discover shops failed:", error);
        // Area is already saved — give user a clear way to continue
        tableBody.innerHTML = `
            <tr><td colspan="3" class="text-center py-4">
                <i class="bi bi-wifi-off text-muted fs-3 d-block mb-2"></i>
                <span class="text-muted small">Auto-discovery unavailable (Google API restriction).</span><br>
                <span class="text-muted small">Your area was saved successfully — you can add shops manually.</span><br>
                <button class="btn btn-sm btn-primary mt-3" onclick="
                    bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
                    if(typeof loadAll === 'function') loadAll();
                "><i class="bi bi-check-circle me-1"></i>Continue — Area Saved</button>
            </td></tr>`;
    }
};

// Add a discovered shop using legacy Places data (no fetchFields needed)
window._addLegacyShop = function (btnEl, place, areaId) {
    btnEl.disabled = true;
    btnEl.textContent = 'Loading...';

    try {
        if (typeof switchModalTab === 'function') switchModalTab('shop');

        document.getElementById('s-name').value = place.name || '';
        document.getElementById('s-addr').value = place.vicinity || '';
        document.getElementById('s-phone').value = '';
        document.getElementById('s-area').value = areaId;
        document.getElementById('s-source').value = 'Google Maps';

        btnEl.className = 'btn btn-sm btn-success fw-semibold text-white disabled';
        btnEl.innerHTML = '<i class="bi bi-check-lg"></i> Pre-filled';
    } catch (error) {
        console.error('Pre-fill failed:', error);
        btnEl.disabled = false;
        btnEl.textContent = 'Add to SRM';
        alert('Could not pre-fill shop details. Please try again.');
    }
};

/**
 * Fetches rich place details from Google and pre-fills the "New Shop" form tab.
 * Does NOT save to the database — the user reviews and submits manually.
 */
window.prepareGoogleShop = async function (btnEl, place_id, areaId) {
    // Give immediate feedback while we fetch
    btnEl.disabled = true;
    btnEl.textContent = 'Loading...';

    try {
        const place = new google.maps.places.Place({ id: place_id });
        await place.fetchFields({
            fields: ['displayName', 'formattedAddress', 'internationalPhoneNumber', 'nationalPhoneNumber']
        });

        // ── Switch modal to New Shop tab ──
        if (typeof switchModalTab === 'function') {
            switchModalTab('shop');
        }

        // ── Pre-fill the shop form fields ──
        document.getElementById('s-name').value = place.displayName || '';
        document.getElementById('s-addr').value = place.formattedAddress || '';
        document.getElementById('s-phone').value = place.internationalPhoneNumber || place.nationalPhoneNumber || '';
        document.getElementById('s-area').value = areaId;

        // Set source to "Google Maps" (option added to HTML select)
        document.getElementById('s-source').value = 'Google Maps';

        // Mark the button so the user can see which row they clicked
        btnEl.className = 'btn btn-sm btn-success fw-semibold text-white disabled';
        btnEl.innerHTML = '<i class="bi bi-check-lg"></i> Pre-filled';
    } catch (error) {
        console.error('getDetails failed:', error);
        btnEl.disabled = false;
        btnEl.textContent = 'Add to SRM';
        alert('Could not retrieve shop details. Please try again.');
    }
};
