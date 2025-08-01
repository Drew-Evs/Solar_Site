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

async function buildEData() {
    const form = document.getElementById('eForm')
    const formData = new FormData(form)
    const params = new URLSearchParams();

    for (const [key, value] of formData.entries()) {
        params.append(key, value)
    }

    const url = `/model_power?${params.toString()}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log("Recieved:", data.time);
    };

    eventSource.onerror = function(err) {
        console.error("SSE connection error:", err)
        eventSource.close();
    };
}
