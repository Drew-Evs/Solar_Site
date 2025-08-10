//builds the grid when data is available
function buildGrid() {
    const table = document.getElementById('grid');

    if (!table) {
        console.log('Table not found');
    }

    const numRows = parseInt(table.dataset.numRows);

    if (!numRows || numRows <= 0) {
        console.log('No valid num_rows found in data attribute:', table.dataset.numRows);
        return;
    }

    table.innerHTML = '';

    for (let r=0; r<numRows; r++) {
        const row = document.createElement('tr');
        
        for (let c = 0; c < 6; c++) {
            const cell = document.createElement('td');
            cell.textContent = `${r+1},${c+1}`;
            
            // Add click handler for toggling clicked state
            cell.addEventListener('click', () => {
                cell.classList.toggle('clicked');
            });
            
            row.appendChild(cell);
        }
        
        table.appendChild(row);
    }
}

//calls build when the page loads
document.addEventListener('DOMContentLoaded', function() {
    buildGrid();
});