async function submitBuildString() {
    const formData = new FormData(document.getElementById('stringForm'))
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
            const imgElement = document.getElementById('img-preview')
            imgElement.src = pixelData.image;
            imgElement.style.display = 'block';
        } else {
            alert('Pixel placement failed: ' + pixelData.message);
        }
    } else {
        alert('Build failed: ' + buildData.message);
    }
}

async function uploadImage() {
    try{
        const formData = new FormData(document.getElementById('imageForm'))
        const imageResponse = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const imageData = await imageResponse.json();
        if (imageData.status === 'success') {
            console.log('Trying to load image from:', imageData.image);
            const imgElement = document.getElementById('img-preview');
            imgElement.src = imageData.image;
            imgElement.style.display = 'block';
        } else {
            console.log('Placing image failed: ' + imageData.message);
        } 
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

let lastEventId = null;

async function buildEData(lastId=null) {
    const form = document.getElementById('eForm');
    const formData = new FormData(form);
    const params = new URLSearchParams();
    
    // Need to save shadow file first
    const fileInput = document.getElementById("pfile");
    const file = fileInput.files[0];
    
    console.log('file is', file);
    
    if (!file) {
        alert("Please select a file");
        return;
    }
    
    try {
        // Then upload
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
            alert("File upload failed: " + uploadResult.error);
            return;
        }
        
        // Manually append all form data except the file
        for (const [key, value] of formData.entries()) {
            if (key !== "pfile") {
                params.append(key, value);
            }
        }
        
        // Use the correct parameter name based on your Flask route
        params.append("pfile", uploadResult.filename);
        params.append("Last-Event-ID", lastId);
        
        // Fix: Use 'timestep' instead of 'time_int' if that's what your form uses
        if (!params.has('time_int') && params.has('timestep')) {
            params.append('time_int', params.get('timestep'));
        }
        
        const url = `/model_power?${params.toString()}`;
        console.log("SSE URL:", url);
        
        // Close any existing EventSource
        if (window.currentEventSource) {
            window.currentEventSource.close();
            window.currentEventSource = null;
        }
        
        const eventSource = new EventSource(url);
        window.currentEventSource = eventSource; // Store reference for cleanup
        
        let connectionEstablished = false;
        
        eventSource.onopen = function(event) {
            console.log("SSE connection opened");
            connectionEstablished = true;
        };
        
        // Queues events when they're called
        eventSource.onmessage = function(event) {
            console.log("Received SSE: ", event.data);
            
            try {
                const data = JSON.parse(event.data);
                
                // Handle error messages
                if (data.error) {
                    console.error("Server error:", data.error);
                    alert("Server error: " + data.error);
                    eventSource.close();
                    window.currentEventSource = null;
                    return;
                }
                
                handleMessage(data);
            } catch (e) {
                console.error("Error parsing SSE data:", e, "Raw data:", event.data);
            }
        };
        
        eventSource.onerror = function(err) {
            console.error("SSE connection error:", err);
            
            if (!connectionEstablished) {
                console.error("Failed to establish initial connection");
                alert("Failed to connect to server. Please check your parameters and try again.");
            }
            
            eventSource.close();
            window.currentEventSource = null;

            //attempts to reconnect
            setTimeout(() => {
                console.log("Reconnectiong SSE")
                buildEData(lastEventId);
            }, 3000);
        };
        
        // Listen for the custom close event
        eventSource.addEventListener('close', function(event) {
            console.log("Server requested close");
            try {
                eventSource.close();
                window.currentEventSource = null;
                console.log("Stream closed successfully.");
            } catch (e) {
                console.error("Error closing stream:", e);
            }
        });
        
        // Set a timeout to prevent hanging connections
        setTimeout(() => {
            if (eventSource.readyState === EventSource.CONNECTING) {
                console.warn("Connection timeout - closing EventSource");
                eventSource.close();
                window.currentEventSource = null;
            }
        }, 70000); // 60 second timeout
        
    } catch (error) {
        console.error("Error in buildEData:", error);
        alert("An error occurred: " + error.message);
    }
}

async function handleMessage(data) {
    // switch case to handle different messages
    switch (data.type) {
        case 'heartbeat':
            console.log("Recieved heartbeat");
            return;
        
        case 'graph_generating':
            console.log("Graphs generating");
            showGraphStatus("Generating graphs...");
            return;

        case 'graphs_ready':
            console.log("Graphs ready", data.graphs);
            displayGraphs(data.graphs);
            showGraphStatus("Generating graphs...");
            return;

        case 'graph_error':
            console.error("Graph generation error:", data.error);
            showGraphStatus("Graph generation failed: " + data.error);
            return;
    }
    
    try {
        const irrLabel = document.getElementById('irradiance-val');
        const pLabel = document.getElementById('power-val');
        const tLabel = document.getElementById('time-val');
        
        if (irrLabel && data.e_info !== undefined) {
            irrLabel.innerHTML = `${data.e_info} W/m<sup>2</sup>`;
        }
        
        if (pLabel && data.pmax !== undefined) {
            pLabel.innerHTML = `${data.pmax} W`;
        }
        
        if (tLabel && data.time !== undefined) {
            // Format the time nicely
            const timeStr = new Date(data.time).toLocaleString();
            tLabel.innerHTML = timeStr;
        }

        if (data.id !== undefined) {
            lastEventId = data.id;
        }
        
        // Wait after each message handle
        await sleep(500);
    } catch (e) {
        console.error("Error handling message: ", e);
    }
}

function displayGraphs(graphPaths) {
    //create the containers for the graph
    let graphContainer = document.getElementById('graph-container')

    if (!graphContainer) {
        graphContainer = document.createElement('div');
        graphContainer.id = 'graph-container';
        graphContainer.innerHTML = '<h3>GeneratedGraphs</h3>'

        //add to the html after the form
        const form = document.getElementById('eForm');
        form.parentNode.insertBefore(graphContainer, form.nextSibling);
    }

    const existingGraphs = graphContainer.querySelectorAll('.graph-image');
    existingGraphs.forEach(graph => graph.remove());

    let pathToProcess = [];

    if (Array.isArray(graphPaths)) {
        pathToProcess = graphPaths.map((path, index) => ({ path, index}));
    }

    pathToProcess.forEach(({path, index}) => {
        const graphDiv = document.createElement('div');
        graphDiv.className = 'graph-image';
        graphDiv.style.marginBottom = '20px';

        const img = document.createElement('img');
        img.src = path;
        img.alt = `Graph ${index + 1}`;
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.style.border = '1px solid #ccc';

        //error handling of images
        img.onerror = function() {
            console.error(`Failed to load graph: ${path}`);
            this.alt = `Failed to load graph ${index + 1}`;
            this.style.backgroundColor = '#f0f0f0';
            this.style.color = '#666';
            this.style.padding = '20px';
            this.style.textAlign = 'center';
        };

        graphDiv.appendChild(img);
        graphContainer.appendChild(graphDiv);
    });

    graphContainer.style.display = 'block';
}

function showGraphStatus(message) {
    let statusDiv = document.getElementById('graph-status');

    //insert if doesnt exist
    if (!statusDiv) {
        statusDiv = document.createElement('div');
        statusDiv.id = 'graph-status';
        statusDiv.style.padding = '10px';
        statusDiv.style.marginTop = '10px';
        statusDiv.style.border = '1px solid #ccc';
        statusDiv.style.backgroundColor = '#f9f9f9';
        
        const form = document.getElementById('eForm');
        form.appendChild(statusDiv);
    }

    statusDiv.textContent = message;

    //hides success after timeout
    if (message.includes("successfully")) {
        setTimeout(() => {
            if (statusDiv.textContent === message) {
                statusDiv.style.display = 'none';
            }
        }, 3000);
    } else {
        statusDiv.style.display = 'block';
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Clean up function to call when page unloads
window.addEventListener('beforeunload', function() {
    if (window.currentEventSource) {
        window.currentEventSource.close();
    }
});