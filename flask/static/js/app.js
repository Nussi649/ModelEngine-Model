// Create the terminal instance
const term = $('#terminal').terminal(async function(command) {
    if (command !== '') {
        try {
            const response = await fetch(executeURL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ command: command })
            });
            const data = await response.json();
            this.echo(data.result);
            updateObjectsTable(data.objects);
        } catch (e) {
            this.error('An error occurred while executing the command.');
        }
    } else {
        this.echo('');
    }
}, {
    greetings: 'Welcome to the terminal interface!\r\n',
    name: 'web_terminal',
    prompt: '$ ',
});

function updateObjectsTable(objects) {
    const objectsTable = document.getElementById('objects-table');
    objectsTable.innerHTML = ''; // Clear existing entries

    for (const section in objects) {
        // Create a section header as a new row
        const headerRow = objectsTable.insertRow();
        const headerCell = headerRow.insertCell(0);
        headerCell.colSpan = 2;  // Span across two columns
        headerCell.textContent = section;
        headerCell.className = "section-header";

        for (const obj of objects[section]) {
            const row = objectsTable.insertRow();
            const cell1 = row.insertCell(0);
            const cell2 = row.insertCell(1);
            cell1.textContent = obj.name;
            cell2.textContent = obj.content;
        }
    }
}