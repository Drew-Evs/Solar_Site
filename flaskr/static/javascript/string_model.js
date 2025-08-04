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
    
    //need to save shadow file first
    const fileInput = document.getElementById("pfile");
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a file");
        return;
    }

    //then upload
    const uploadData = new FormData();
    uploadData.append("pfile", file);

    const uploadResponse = await fetch("/save_shade_file", {
        method: "POST",
        body: uploadData
    });

    const uploadResult = await uploadResponse.json();

    if (uploadResult.error) {
        console.error("File upload failed:", uploadResult.error);
        return;
    }

    //manually append shadow file
    for (const [key, value] of formData.entries()) {
        if (key != "pfile") {
            params.append(key, value)
        }
    }

    params.append("pfile", uploadResult.filename);

    const url = `/model_power?${params.toString()}`;
    const eventSource = new EventSource(url);

    //queue messages to handle in order
    const messageQueue = [];

    let processing = false;

    async function processQueue() {
        //lock and key
        if (processing) return;
        processing = true;

        while (messageQueue.length > 0) {
            //pop off the queue
            const event = messageQueue.shift();
            await handleMessage(event);
        }
        processing = false;
    }
    
    //queues events when theyre called
    eventSource.onmessage = function(event) {
        messageQueue.push(event);
        processQueue();
    };
    
    eventSource.onerror = function(err) {
        console.error("SSE connection error:", err)
        eventSource.close();
    };

    eventSource.addEventListener('close', function() {
        source.close();
        console.log("Stream closed.");
    });
}

async function handleMessage(event) {
    const data = JSON.parse(event.data);

    const irrLabel = document.getElementById('irradiance-val');
    irrLabel.innerHTML = `${data.e_info} W/m<sup>2</sup>`;
    
    const pLabel = document.getElementById('power-val');
    pLabel.innerHTML = `${data.pmax} W`;

    const tLabel = document.getElementById('time-val');
    tLabel.innerHTML = `${data.time}`;

    //wait after each message handle
    await sleep(500);
};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
