async function buildData(formData=null) {
    try {
        console.log("Form data",formData)
        let buildResponse;
        if (formData) {
            buildResponse = await fetch('/build_data', {
                method: 'POST',
                body: formData
            });
        } else {
            buildResponse = await fetch('/build_data', {
                method: 'POST'
            });
        }

        const data = await buildResponse.json();

        console.log("Response data",data)

        const tbody = document.querySelector('#panel-table tbody')
        tbody.innerHTML = '';

        data.forEach(panel => {
            const row = document.createElement('tr');
            
            //creating cells
            ['name', 'length', 'width', 'cells', 'power'].forEach(key=> {
                const cell = document.createElement('td');
                cell.textContent = panel[key];
                cell.contentEditable = (key !== 'name' && key !== 'power');
                row.appendChild(cell);
            });

            //select a single row - removing prev selection
            row.addEventListener('click', () => {
                tbody.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
                console.log('Selected panel:', panel.name);
            });

            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Failed to load data: ',error);
    }

}

async function filterTable() {
    const formData = new FormData(document.getElementById('filterForm'));
    buildData(formData);
}

async function calcPower() {
    //empty form data to add to
    const formData = new FormData();
    const tbody = document.querySelector('#panel-table tbody')
    tbody.querySelectorAll('tr.selected').forEach(row => {
        const panelName = row.cells[0].textContent;
        formData.append('panel_name', panelName);
        console.log("Name is ", panelName);
    });

    const powerResponse = await fetch('/calc_power', {
        method: 'POST',
        body: formData
    });

    const powerData = await powerResponse.json();

    tbody.querySelectorAll('tr.selected').forEach(row => {
        row.cells[4].textContent = powerData.power
    });
    
}

async function newPanel() {
    const form = document.getElementById('newForm')
    const formData = new FormData(form)

    const pyResponse = await fetch('/new_panel', {
            method: 'POST',
            body: formData
         });
    
    const pyData = await buildResponse.json();

    if (pyData.status === 'success') {
        console.log(`New panel ${pyData.panelName}`)
    } else {
        console.log(`Error with new panel ${pyData.message}`)
    }

}

window.onload = buildData;