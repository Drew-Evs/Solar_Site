// Global variables
let lastEventId = null;

// Initialize page when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeFileInputs();
});

// File input initialization and display
function initializeFileInputs() {
    // Enhanced file input display for background image
    document.getElementById('file').addEventListener('change', function(e) {
        const fileName = e.target.files[0]?.name || '';
        document.getElementById('file-name').textContent = fileName ? `Selected: ${fileName}` : '';
    });

    // Enhanced file input display for CSV file
    document.getElementById('pfile').addEventListener('change', function(e) {
        const fileName = e.target.files[0]?.name || '';
        document.getElementById('pfile-name').textContent = fileName ? `Selected: ${fileName}` : '';
    });
}

// Image upload functionality
async function uploadImage() {
    try {
        const formData = new FormData(document.getElementById('imageForm'));
        
        // Check if file is selected
        const fileInput = document.getElementById('file');
        if (!fileInput.files[0]) {
            showStatus('Please select an image file first', 'error');
            return;
        }
        
        const imageResponse = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const imageData = await imageResponse.json();
        if (imageData.status === 'success') {
            console.log('Trying to load image from:', imageData.image);
            const imgElement = document.getElementById('img-preview');
            const placeholder = document.getElementById('preview-placeholder');
            
            imgElement.src = imageData.image;
            imgElement.style.display = 'block';
            placeholder.style.display = 'none';
            
            showStatus('Image uploaded successfully!', 'success');
        } else {
            showStatus('Image upload failed: ' + imageData.message, 'error');
        } 
    } catch (error) {
        console.error('Upload error:', error);
        showStatus('Error: ' + error.message, 'error');
    }
}

// String building functionality
async function submitBuildString() {
    try {
        const formData = new FormData(document.getElementById('stringForm'));
        const buildResponse = await fetch('/build_string', {
            method: 'POST',
            body: formData
        });

        const buildData = await buildResponse.json();
        if (buildData.status === 'success') {
            const pixelResponse = await fetch('/place_pixels', {
                method: 'POST'
            });

            const pixelData = await pixelResponse.json();
            if (pixelData.status === 'success') {
                console.log('Trying to load image from:', pixelData.image);
                const imgElement = document.getElementById('img-preview');
                const placeholder = document.getElementById('preview-placeholder');
                
                imgElement.src = pixelData.image;
                imgElement.style.display = 'block';
                placeholder.style.display = 'none';
                
                // Update string info section
                updateStringInfo(formData, buildData.power);
                
                showStatus('String built successfully!', 'success');
            } else {
                showStatus('Pixel placement failed: ' + pixelData.message, 'error');
            }
        } else {
            showStatus('Build failed: ' + buildData.message, 'error');
        }
    } catch (error) {
        console.error('Build string error:', error);
        showStatus('Error building string: ' + error.message, 'error');
    }
}

// Update string information display
function updateStringInfo(formData, power) {
    const stringInfoDiv = document.getElementById('string-info');
    const panelName = formData.get('panel_name') || 'Unknown Panel';
    const panelCount = formData.get('panel_count') || '0';
    const rotation = formData.get('rotation') || '0';
    const xCoord = formData.get('X') || '0';
    const yCoord = formData.get('Y') || '0';
    
    stringInfoDiv.innerHTML = `
        <div style="width: 100%;">
            <form id="PEForm">
                <div style="margin-bottom: 1rem;">
                    <strong>Panel Model:</strong><br>
                    <span style="font-size: 0.9rem; color: #666;">${panelName}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div><strong>Panel Count:</strong><br>${panelCount}</div>
                    <div id="original-power"><strong>Max Panel Power:</strong><br>${power}W</div>
                    <div><strong>Expected Power:</strong><br><button type="button" class="button-secondary" onclick="editPower()" id="update-power-button">
                    <span id="edit-button-text">Alter Power</span></button></div>
                    <div class="input-group">
                        <label for="update_power" style="font-weight: 700;">Actual Power:</label>
                        <input type="number" id="update_power" name="update_power" min="10" max="1000" step="1" value="{{ update_power or 0 }}">
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div><strong>Rotation:</strong><br>${rotation}°</div>
                    <div><strong>X Position:</strong><br>${xCoord}</div>
                    <div><strong>Y Position:</strong><br>${yCoord}</div>
                </form>
            </div>
        </div>
    `;
    stringInfoDiv.style.color = '#333';
    stringInfoDiv.style.fontStyle = 'normal';
}

// Main power modeling function
async function buildEData(lastId = null) {
    // Hide graphs and show loading state
    hideGraphs();
    showLoadingState(true);
    hideRealTimeData();
    
    const form = document.getElementById('eForm');
    const formData = new FormData(form);
    const params = new URLSearchParams();
    
    // Validate required inputs
    if (!validateInputs(formData)) {
        showLoadingState(false);
        return;
    }
    
    const fileInput = document.getElementById("pfile");
    const file = fileInput.files[0];
    
    if (!file) {
        showStatus("Please select a CSV file", 'error');
        showLoadingState(false);
        return;
    }
    
    try {
        // Upload the shadow file first
        const uploadResult = await uploadShadowFile(file);
        if (!uploadResult) {
            showLoadingState(false);
            return;
        }
        
        // Prepare parameters for SSE request
        prepareSSEParams(formData, params, uploadResult.filename, lastId);
        
        // Start Server-Sent Events connection
        startSSEConnection(params);
        
    } catch (error) {
        console.error("Error in buildEData:", error);
        showStatus("An error occurred: " + error.message, 'error');
        showLoadingState(false);
    }
}

// Validate form inputs
function validateInputs(formData) {
    const startDate = formData.get('start');
    const endDate = formData.get('end');
    const timeInt = formData.get('time_int');
    const lat = formData.get('lat');
    const lon = formData.get('lon');
    
    if (!startDate || !endDate) {
        showStatus("Please select both start and end dates", 'error');
        return false;
    }
    
    if (!timeInt || timeInt < 1) {
        showStatus("Please enter a valid time step (minimum 1)", 'error');
        return false;
    }
    
    if (lat < -90 || lat > 90) {
        showStatus("Latitude must be between -90 and 90", 'error');
        return false;
    }
    
    if (lon < -180 || lon > 180) {
        showStatus("Longitude must be between -180 and 180", 'error');
        return false;
    }
    
    return true;
}

// Upload shadow file to server
async function uploadShadowFile(file) {
    try {
        const uploadData = new FormData();
        uploadData.append("pfile", file);
        
        const uploadResponse = await fetch("/save_shade_file", {
            method: "POST",
            body: uploadData
        });
        
        if (!uploadResponse.ok) {
            throw new Error(`Upload failed: ${uploadResponse.status}`);
        }
        
        const uploadResult = await uploadResponse.json();
        
        if (uploadResult.error) {
            console.error("File upload failed:", uploadResult.error);
            showStatus("File upload failed: " + uploadResult.error, 'error');
            return null;
        }
        
        return uploadResult;
    } catch (error) {
        console.error("Shadow file upload error:", error);
        showStatus("Failed to upload file: " + error.message, 'error');
        return null;
    }
}

// Prepare parameters for SSE request
function prepareSSEParams(formData, params, filename, lastId) {
    // Add all form data except the file
    for (const [key, value] of formData.entries()) {
        if (key !== "pfile") {
            params.append(key, value);
        }
    }
    
    // Add uploaded filename and event ID
    params.append("pfile", filename);
    params.append("Last-Event-ID", lastId);
    
    // Handle timestep parameter compatibility
    if (!params.has('time_int') && params.has('timestep')) {
        params.append('time_int', params.get('timestep'));
    }
}

// Start Server-Sent Events connection
function startSSEConnection(params) {
    const url = `/model_power?${params.toString()}`;
    console.log("SSE URL:", url);
    
    // Close any existing connection
    if (window.currentEventSource) {
        window.currentEventSource.close();
        window.currentEventSource = null;
    }
    
    const eventSource = new EventSource(url);
    window.currentEventSource = eventSource;
    
    let connectionEstablished = false;
    
    // Connection opened
    eventSource.onopen = function(event) {
        console.log("SSE connection opened");
        connectionEstablished = true;
        showRealTimeData();
    };
    
    // Handle incoming messages
    eventSource.onmessage = function(event) {
        console.log("Received SSE: ", event.data);
        
        try {
            const data = JSON.parse(event.data);
            
            if (data.error) {
                console.error("Server error:", data.error);
                showStatus("Server error: " + data.error, 'error');
                closeEventSource(eventSource);
                return;
            }
            
            handleMessage(data);
        } catch (e) {
            console.error("Error parsing SSE data:", e, "Raw data:", event.data);
        }
    };
    
    // Handle connection errors
    eventSource.onerror = function(err) {
        console.error("SSE connection error:", err);
        
        if (!connectionEstablished) {
            console.error("Failed to establish initial connection");
            showStatus("Failed to connect to server. Please check your parameters and try again.", 'error');
            showLoadingState(false);
        }
        
        closeEventSource(eventSource);

        // Attempt to reconnect after delay
        setTimeout(() => {
            console.log("Attempting to reconnect SSE");
            buildEData(lastEventId);
        }, 3000);
    };
    
    // Handle server-requested close
    eventSource.addEventListener('close', function(event) {
        console.log("Server requested close");
        closeEventSource(eventSource);
        showStatus("Analysis completed successfully!", 'success');
        console.log("Stream closed successfully.");
    });
    
    // Set connection timeout
    setTimeout(() => {
        if (eventSource.readyState === EventSource.CONNECTING) {
            console.warn("Connection timeout - closing EventSource");
            closeEventSource(eventSource);
            showStatus("Connection timeout", 'error');
        }
    }, 70000);
}

// Close EventSource connection and update UI
function closeEventSource(eventSource) {
    try {
        eventSource.close();
        window.currentEventSource = null;
        showLoadingState(false);
    } catch (e) {
        console.error("Error closing EventSource:", e);
    }
}

// Handle incoming SSE messages
async function handleMessage(data) {
    // Handle different message types
    switch (data.type) {
        case 'heartbeat':
            console.log("Received heartbeat");
            return;
        
        case 'graph_generating':
            console.log("Graphs generating");
            showStatus("Generating graphs...", 'info');
            return;

        case 'graphs_ready':
            console.log("Graphs ready", data.graphs);
            displayGraphs(data.graphs, data.shadedPower, data.unshadedPower);
            showStatus("Graphs generated successfully!", 'success');
            return;

        case 'graph_error':
            console.error("Graph generation error:", data.error);
            showStatus("Graph generation failed: " + data.error, 'error');
            return;
    }
    
    // Handle real-time data updates
    try {
        updateRealTimeData(data);
        
        // Store event ID for reconnection
        if (data.id !== undefined) {
            lastEventId = data.id;
        }
        
        // Small delay between message processing
        await sleep(500);
    } catch (e) {
        console.error("Error handling message: ", e);
    }
}

// Update real-time data display
function updateRealTimeData(data) {
    const irrLabel = document.getElementById('irradiance-val');
    const pLabel = document.getElementById('power-val');
    const tLabel = document.getElementById('time-val');
    const cLabel = document.getElementById('temp-val');
    
    if (irrLabel && data.e_info !== undefined) {
        irrLabel.innerHTML = `${data.e_info} W/m²`;
    }
    
    if (pLabel && data.pmax !== undefined) {
        pLabel.innerHTML = `${data.pmax} W`;
    }
    
    if (tLabel && data.time !== undefined) {
        tLabel.innerHTML = data.time;
    }

    if (tLabel && data.temp !== undefined) {
        cLabel.innerHTML = `${data.temp} °C`;
    }
}

// Display generated graphs
function displayGraphs(graphPaths, shadedPower, unshadedPower) {
    let graphContainer = document.getElementById('graph-container');
    let graphGrid = document.getElementById('graph-grid');
    const powerInfoDiv = document.createElement('div');
    powerInfoDiv.innerHTML = ''
    
    // Clear existing graphs
    graphGrid.innerHTML = '';
    
    let pathToProcess = [];
    if (Array.isArray(graphPaths)) {
        pathToProcess = graphPaths.map((path, index) => ({ path, index}));
    }

    pathToProcess.forEach(({path, index}) => {
        const graphDiv = document.createElement('div');
        graphDiv.className = 'graph-item';

        const img = document.createElement('img');
        img.src = path;
        img.alt = `Graph ${index + 1}`;
        img.loading = 'lazy'; // Improve performance

        // Handle image load errors
        img.onerror = function() {
            console.error(`Failed to load graph: ${path}`);
            this.alt = `Failed to load graph ${index + 1}`;
            this.style.backgroundColor = '#f0f0f0';
            this.style.color = '#666';
            this.style.padding = '20px';
            this.style.textAlign = 'center';
            this.style.border = '2px dashed #ccc';
        };

        // Add click handler for full-size view (optional enhancement)
        img.addEventListener('click', function() {
            openImageModal(path, `Graph ${index + 1}`);
        });

        graphDiv.appendChild(img);
        graphGrid.appendChild(graphDiv);
    });

    //add the power info to the bottom
    powerInfoDiv.className = "grid-item";

    powerInfoDiv.innerHTML = `
    <h2 class="section-title">⚡ Power Information</h2>
    <div style="display: flex; align-items: flex-start; justify-content: space-around; width: 100%; padding: 20px; color: #666; font-style: italic;">
        <div style="text-align: center;">
            <div style="margin-bottom: 2rem; font-size: 1.2rem;">
                <strong>Shaded Power Output:</strong><br>
                <span style="font-size: 1.4rem; color: #333;">${shadedPower} kWh</span>
            </div>
        </div>
        <div style="text-align: center;">
            <div style="margin-bottom: 2rem; font-size: 1.2rem;">
                <strong>Unshaded Power Output:</strong><br>
                <span style="font-size: 1.4rem; color: #333;">${unshadedPower} kWh</span>
            </div>
        </div>
    </div>
    `;
    powerInfoDiv.style.color = '#333';
    powerInfoDiv.style.fontStyle = 'normal';

    //add it to the graph container
    graphContainer.appendChild(powerInfoDiv);

    // Show the graph container
    graphContainer.style.display = 'block';
}

// Optional: Open image in modal for full-size viewing
function openImageModal(imageSrc, altText) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
        cursor: pointer;
    `;
    
    // Create modal image
    const modalImg = document.createElement('img');
    modalImg.src = imageSrc;
    modalImg.alt = altText;
    modalImg.style.cssText = `
        max-width: 90%;
        max-height: 90%;
        object-fit: contain;
        border-radius: 8px;
    `;
    
    modal.appendChild(modalImg);
    document.body.appendChild(modal);
    
    // Close modal on click
    modal.addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Close modal on escape key
    const handleKeyPress = (e) => {
        if (e.key === 'Escape') {
            document.body.removeChild(modal);
            document.removeEventListener('keydown', handleKeyPress);
        }
    };
    document.addEventListener('keydown', handleKeyPress);
}

// Hide graphs container
function hideGraphs() {
    const graphContainer = document.getElementById('graph-container');
    const graphGrid = document.getElementById('graph-grid');
    graphContainer.style.display = 'none';
    graphGrid.innerHTML = '';
}

// Show/hide loading state on button
function showLoadingState(isLoading) {
    const button = document.getElementById('model-button');
    const spinner = document.getElementById('loading-spinner');
    const buttonText = document.getElementById('button-text');
    
    if (isLoading) {
        button.disabled = true;
        spinner.style.display = 'block';
        buttonText.textContent = 'Processing...';
        button.style.cursor = 'not-allowed';
    } else {
        button.disabled = false;
        spinner.style.display = 'none';
        buttonText.textContent = '🚀 Model Power Over Time';
        button.style.cursor = 'pointer';
    }
}

// Show/hide real-time data section
function showRealTimeData() {
    document.getElementById('real-time-data').style.display = 'grid';
}

function hideRealTimeData() {
    document.getElementById('real-time-data').style.display = 'none';
}

// Display status messages
function showStatus(message, type = 'info') {
    const statusDiv = document.getElementById('graph-status');
    
    // Clear existing classes and add new ones
    statusDiv.className = `status-message ${type}-message`;
    statusDiv.textContent = message;
    statusDiv.style.display = 'flex';

    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            if (statusDiv.textContent === message) {
                statusDiv.style.display = 'none';
            }
        }, 3000);
    }
}

// Utility function for delays
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (window.currentEventSource) {
        window.currentEventSource.close();
        window.currentEventSource = null;
    }
});

// Error handling for uncaught errors
window.addEventListener('error', function(e) {
    console.error('Uncaught error:', e.error);
    showStatus('An unexpected error occurred. Please refresh the page and try again.', 'error');
});

// Handle fetch errors globally
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    showStatus('Network error occurred. Please check your connection and try again.', 'error');
});

// Utility functions for form validation
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function isValidDate(dateString) {
    const date = new Date(dateString);
    return date instanceof Date && !isNaN(date);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function editPower() {
    const form = document.getElementById('PEForm');
    const formData = new FormData(form);

    //get the new and original power
    const newPower = formData.get('update_power');
    const powerDiv = document.getElementById('original-power');
    //needs to remove the w - matches numbers
    const powerText = powerDiv.textContent || powerDiv.innerText;
    const powerNumber = powerText.match(/[\d.]+/)[0];  
    const originalPower = parseFloat(powerNumber);       

    formData.append('original_power', originalPower)

    const updateResponse = await fetch('/update_power', {
        method: 'POST',
        body: formData
    });

    const updateData = await updateResponse.json();

    if (updateData.status === "success") {
        powerDiv.innerHTML = `<div id="original-power"><strong>Max Panel Power:</strong><br>${updateData.new_power}W</div>`
    }
}