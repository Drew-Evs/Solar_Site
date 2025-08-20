// Enhanced grid.js with modern UI feedback and animations

// Utility functions for UI feedback
function showMessage(type, message, duration = 5000) {
    // Hide all messages first
    ['success-message', 'error-message', 'info-message'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.style.display = 'none';
    });

    // Show the specific message
    const messageElement = document.getElementById(`${type}-message`);
    const textElement = document.getElementById(`${type}-text`);
    
    if (messageElement && textElement) {
        textElement.textContent = message;
        messageElement.style.display = 'flex';
        
        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => {
                messageElement.style.display = 'none';
            }, duration);
        }
    }
}

function setLoadingState(button, isLoading, originalText = '') {
    if (isLoading) {
        button.disabled = true;
        button.dataset.originalText = button.querySelector('span').textContent;
        button.innerHTML = `
            <div class="loading-spinner" style="display: block;"></div>
            <span>Processing...</span>
        `;
    } else {
        button.disabled = false;
        const text = originalText || button.dataset.originalText || 'Submit';
        button.innerHTML = `<span>${text}</span>`;
    }
}

function animateTableUpdate() {
    const tbody = document.querySelector('#panel-table tbody');
    if (tbody) {
        tbody.style.opacity = '0.5';
        tbody.style.transform = 'translateY(10px)';
        
        setTimeout(() => {
            tbody.style.transition = 'all 0.3s ease';
            tbody.style.opacity = '1';
            tbody.style.transform = 'translateY(0)';
        }, 100);
    }
}

async function buildData(formData = null) {
    const filterButton = document.querySelector('button[onclick="filterTable()"]');
    
    try {
        console.log("Form data", formData);
        
        if (filterButton) {
            setLoadingState(filterButton, true, '🔍 Filter Results');
        }
        
        showMessage('info', 'Loading panel data...', 0);
        
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

        if (!buildResponse.ok) {
            throw new Error(`HTTP error! status: ${buildResponse.status}`);
        }

        const data = await buildResponse.json();
        console.log("Response data", data);

        const tbody = document.querySelector('#panel-table tbody');
        if (!tbody) {
            throw new Error('Table body not found');
        }

        // Clear existing data with animation
        tbody.style.opacity = '0.5';
        setTimeout(() => {
            tbody.innerHTML = '';

            if (data.length === 0) {
                const row = document.createElement('tr');
                const cell = document.createElement('td');
                cell.colSpan = 5;
                cell.textContent = 'No panels found matching your criteria';
                cell.style.textAlign = 'center';
                cell.style.fontStyle = 'italic';
                cell.style.color = 'var(--text-secondary)';
                row.appendChild(cell);
                tbody.appendChild(row);
            } else {
                data.forEach((panel, index) => {
                    const row = document.createElement('tr');
                    row.style.opacity = '0';
                    row.style.transform = 'translateY(20px)';
                    
                    // Create cells
                    ['name', 'length', 'width', 'cells', 'power'].forEach(key => {
                        const cell = document.createElement('td');
                        cell.textContent = panel[key];
                        cell.contentEditable = (key !== 'name' && key !== 'power');
                        
                        // Add input styling for editable cells
                        if (cell.contentEditable === 'true') {
                            cell.style.cursor = 'text';
                            cell.addEventListener('focus', function() {
                                this.style.background = 'rgba(102, 126, 234, 0.05)';
                                this.style.outline = '2px solid var(--accent-color)';
                                this.style.borderRadius = '4px';
                            });
                            cell.addEventListener('blur', function() {
                                this.style.background = '';
                                this.style.outline = '';
                                this.style.borderRadius = '';
                            });
                        }
                        
                        row.appendChild(cell);
                    });

                    // Add row selection functionality with enhanced feedback
                    row.addEventListener('click', () => {
                        // Remove previous selection
                        tbody.querySelectorAll('tr.selected').forEach(r => {
                            r.classList.remove('selected');
                        });
                        
                        // Add selection with animation
                        row.classList.add('selected');
                        row.style.transform = 'scale(1.01)';
                        setTimeout(() => {
                            row.style.transform = '';
                        }, 150);
                        
                        console.log('Selected panel:', panel.name);
                        showMessage('info', `Selected panel: ${panel.name}`, 3000);
                    });

                    tbody.appendChild(row);
                    
                    // Stagger animation for each row
                    setTimeout(() => {
                        row.style.transition = 'all 0.3s ease';
                        row.style.opacity = '1';
                        row.style.transform = 'translateY(0)';
                    }, index * 50 + 100);
                });
            }

            // Restore table opacity
            setTimeout(() => {
                tbody.style.opacity = '1';
            }, 200);
        }, 200);

        showMessage('success', `Loaded ${data.length} panel(s) successfully`, 3000);

    } catch (error) {
        console.error('Failed to load data:', error);
        showMessage('error', `Failed to load data: ${error.message}`);
        
        const tbody = document.querySelector('#panel-table tbody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--danger-color); font-style: italic;">
                        ❌ Error loading data. Please try again.
                    </td>
                </tr>
            `;
            tbody.style.opacity = '1';
        }
    } finally {
        if (filterButton) {
            setLoadingState(filterButton, false, '🔍 Filter Results');
        }
        
        // Hide info message after delay
        setTimeout(() => {
            const infoMessage = document.getElementById('info-message');
            if (infoMessage && infoMessage.style.display === 'flex') {
                infoMessage.style.display = 'none';
            }
        }, 1000);
    }
}

async function filterTable() {
    try {
        const formData = new FormData(document.getElementById('filterForm'));
        await buildData(formData);
    } catch (error) {
        console.error('Filter error:', error);
        showMessage('error', 'Failed to filter panels. Please try again.');
    }
}

async function calcPower() {
    const calcButton = document.querySelector('button[onclick="calcPower()"]');
    
    try {
        setLoadingState(calcButton, true, '⚡ Calculate Power');
        showMessage('info', 'Calculating power...', 0);
        
        const formData = new FormData();
        const tbody = document.querySelector('#panel-table tbody');
        const selectedRows = tbody.querySelectorAll('tr.selected');
        
        if (selectedRows.length === 0) {
            showMessage('error', 'Please select a panel from the table first');
            return;
        }
        
        selectedRows.forEach(row => {
            const panelName = row.cells[0].textContent;
            formData.append('panel_name', panelName);
            console.log("Calculating power for:", panelName);
        });

        const powerResponse = await fetch('/calc_power', {
            method: 'POST',
            body: formData
        });

        if (!powerResponse.ok) {
            throw new Error(`HTTP error! status: ${powerResponse.status}`);
        }

        const powerData = await powerResponse.json();
        console.log("Power calculation result:", powerData);

        // Update the power values with animation
        selectedRows.forEach(row => {
            const powerCell = row.cells[4];
            const oldValue = powerCell.textContent;
            
            // Add highlight animation
            powerCell.style.background = 'rgba(16, 185, 129, 0.2)';
            powerCell.style.transform = 'scale(1.05)';
            powerCell.textContent = powerData.power;
            
            setTimeout(() => {
                powerCell.style.transition = 'all 0.3s ease';
                powerCell.style.background = '';
                powerCell.style.transform = '';
            }, 500);
        });
        
        showMessage('success', `Power calculated: ${powerData.power}W`);
        
    } catch (error) {
        console.error('Power calculation failed:', error);
        showMessage('error', `Power calculation failed: ${error.message}`);
    } finally {
        setLoadingState(calcButton, false, '⚡ Calculate Power');
        
        // Hide info message
        setTimeout(() => {
            const infoMessage = document.getElementById('info-message');
            if (infoMessage && infoMessage.style.display === 'flex') {
                infoMessage.style.display = 'none';
            }
        }, 1000);
    }
}

async function updateDB() {
    const updateButton = document.querySelector('button[onclick="updateDB()"]');
    
    try {
        setLoadingState(updateButton, true, '💾 Save Changes');
        showMessage('info', 'Saving changes...', 0);
        
        const formData = new FormData();
        const tbody = document.querySelector('#panel-table tbody');
        const selectedRows = tbody.querySelectorAll('tr.selected');
        
        if (selectedRows.length === 0) {
            showMessage('error', 'Please select a panel to update');
            return;
        }
        
        selectedRows.forEach(row => {
            const panelName = row.cells[0].textContent;
            const length = row.cells[1].textContent;
            const width = row.cells[2].textContent;
            const cells = row.cells[3].textContent;
            
            formData.append('panel_name', panelName);
            formData.append('length', length);
            formData.append('width', width);
            formData.append('cells', cells);
        });

        const updateResponse = await fetch('/update_panel', {
            method: 'POST',
            body: formData
        });

        if (!updateResponse.ok) {
            throw new Error(`HTTP error! status: ${updateResponse.status}`);
        }

        const result = await updateResponse.json();
        
        if (result.status === 'success') {
            showMessage('success', 'Panel updated successfully!');
            
            // Add success animation to selected rows
            selectedRows.forEach(row => {
                row.style.background = 'rgba(16, 185, 129, 0.1)';
                setTimeout(() => {
                    row.style.background = '';
                }, 2000);
            });
        } else {
            throw new Error(result.message || 'Update failed');
        }
        
    } catch (error) {
        console.error('Update failed:', error);
        showMessage('error', `Update failed: ${error.message}`);
    } finally {
        setLoadingState(updateButton, false, '💾 Save Changes');
        
        setTimeout(() => {
            const infoMessage = document.getElementById('info-message');
            if (infoMessage && infoMessage.style.display === 'flex') {
                infoMessage.style.display = 'none';
            }
        }, 1000);
    }
}

async function newPanel() {
    const newButton = document.querySelector('button[onclick="newPanel()"]');
    
    try {
        setLoadingState(newButton, true, '✨ Create New Panel');
        showMessage('info', 'Creating new panel...', 0);
        
        const form = document.getElementById('newForm');
        const formData = new FormData(form);
        
        // Basic validation
        const panelName = formData.get('panel_name');
        if (!panelName || panelName.trim() === '') {
            throw new Error('Panel name is required');
        }

        const pyResponse = await fetch('/new_panel', {
            method: 'POST',
            body: formData
        });

        if (!pyResponse.ok) {
            throw new Error(`HTTP error! status: ${pyResponse.status}`);
        }

        const pyData = await pyResponse.json();

        if (pyData.status === 'success') {
            showMessage('success', `New panel "${pyData.panelName || panelName}" created successfully!`);
            
            // Clear form with animation
            const inputs = form.querySelectorAll('input, select');
            inputs.forEach((input, index) => {
                setTimeout(() => {
                    if (input.type !== 'number') {
                        input.value = '';
                    } else {
                        input.value = input.placeholder || '';
                    }
                    input.style.background = 'rgba(16, 185, 129, 0.05)';
                    setTimeout(() => {
                        input.style.background = '';
                    }, 300);
                }, index * 50);
            });
            
            // Refresh the panel list
            setTimeout(() => buildData(), 1000);
            
        } else {
            throw new Error(pyData.message || 'Panel creation failed');
        }

    } catch (error) {
        console.error('New panel creation failed:', error);
        showMessage('error', `Panel creation failed: ${error.message}`);
    } finally {
        setLoadingState(newButton, false, '✨ Create New Panel');
        
        setTimeout(() => {
            const infoMessage = document.getElementById('info-message');
            if (infoMessage && infoMessage.style.display === 'flex') {
                infoMessage.style.display = 'none';
            }
        }, 1000);
    }
}

function clearForm() {
    const form = document.getElementById('newForm');
    const inputs = form.querySelectorAll('input, select');
    
    inputs.forEach((input, index) => {
        setTimeout(() => {
            if (input.type === 'select-one') {
                input.selectedIndex = 0;
            } else if (input.type === 'number') {
                input.value = input.placeholder || '';
            } else {
                input.value = '';
            }
            
            // Add clear animation
            input.style.background = 'rgba(102, 126, 234, 0.05)';
            input.style.transform = 'scale(0.98)';
            setTimeout(() => {
                input.style.background = '';
                input.style.transform = '';
            }, 200);
        }, index * 30);
    });
    
    showMessage('info', 'Form cleared successfully', 2000);
}

// Enhanced initialization
window.addEventListener('load', async () => {
    console.log('Panel modeling interface loaded');
    
    // Show loading message
    showMessage('info', 'Initializing panel data...', 0);
    
    try {
        await buildData();
    } catch (error) {
        console.error('Initial data load failed:', error);
        showMessage('error', 'Failed to load initial data. Please refresh the page.');
    }
    
    // Add enhanced form interactions
    const inputs = document.querySelectorAll('input, select');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.style.transform = 'translateY(-1px)';
        });
        
        input.addEventListener('blur', function() {
            this.style.transform = '';
        });
    });
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 'f':
                    e.preventDefault();
                    document.getElementById('panel-input').focus();
                    break;
                case 's':
                    e.preventDefault();
                    const selectedRow = document.querySelector('#panel-table tbody tr.selected');
                    if (selectedRow) {
                        updateDB();
                    }
                    break;
                case 'n':
                    e.preventDefault();
                    document.getElementById('panel_name').focus();
                    break;
            }
        }
    });
    
    console.log('Enhanced panel interface ready! Keyboard shortcuts: Ctrl+F (filter), Ctrl+S (save), Ctrl+N (new panel)');
});