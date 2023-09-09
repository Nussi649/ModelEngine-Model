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
    greetings: 'Welcome to the terminal interface!',
    name: 'web_terminal',
    prompt: '\r\n$ ',
});

function updateObjectsTable(objects) {
    // Model Objects Table
    const modelObjectsTable = document.getElementById('model-objects-content');
    modelObjectsTable.innerHTML = ''; // Clear existing entries

    for (const objectType in objects.model_objects) {
        // Create a section header as a new row
        const sectionHeaderRow = modelObjectsTable.insertRow();
        const sectionHeaderCell = sectionHeaderRow.insertCell(0);
        sectionHeaderCell.colSpan = 2;
        sectionHeaderCell.textContent = objectType;
        sectionHeaderCell.className = "section-header";

        for (const obj of objects.model_objects[objectType]) {
            const row = modelObjectsTable.insertRow();
            const cell1 = row.insertCell(0);
            const cell2 = row.insertCell(1);
            cell1.textContent = obj.name;
            cell2.textContent = obj.content;
        }
    }

    // Runtime Objects - Lists
    const listsTable = document.getElementById('lists-content');
    listsTable.innerHTML = '';

    for (const listObj of objects.runtime_objects.lists) {
        const sectionHeaderRow = listsTable.insertRow();
        const sectionHeaderCell = sectionHeaderRow.insertCell(0);
        sectionHeaderCell.colSpan = 2;
        sectionHeaderCell.textContent = listObj.name;
        sectionHeaderCell.className = "section-header";

        for (const item of listObj.content) {
            const row = listsTable.insertRow();
            const cell1 = row.insertCell(0);
            const cell2 = row.insertCell(1);
            cell1.textContent = item.type;
            cell2.textContent = item.value;
        }
    }

    // Runtime Objects - Dicts
    const dictsTable = document.getElementById('dicts-content');
    dictsTable.innerHTML = '';

    for (const dictObj of objects.runtime_objects.dicts) {
        const sectionHeaderRow = dictsTable.insertRow();
        const sectionHeaderCell = sectionHeaderRow.insertCell(0);
        sectionHeaderCell.colSpan = 3;
        sectionHeaderCell.textContent = dictObj.name;
        sectionHeaderCell.className = "section-header";

        for (const pair of dictObj.content) {
            const row = dictsTable.insertRow();
            const cell1 = row.insertCell(0);
            const cell2 = row.insertCell(1);
            const cell3 = row.insertCell(2);
            cell1.textContent = pair.key;
            cell2.textContent = pair.type;
            cell3.textContent = pair.value;
        }
    }

    // Runtime Objects - Variables
    const variablesTable = document.getElementById('variables-content');
    variablesTable.innerHTML = '';

    for (const varObj of objects.runtime_objects.variables) {
        const row = variablesTable.insertRow();
        const cell1 = row.insertCell(0);
        const cell2 = row.insertCell(1);
        cell1.textContent = varObj.name;
        cell2.textContent = `${varObj.type}: ${varObj.content}`;
    }

    // Check and reveal divs if they have data
    if ($("#lists-table tbody tr").length > 0) {
        $("#lists-div").show();
    }
    if ($("#dicts-table tbody tr").length > 0) {
        $("#dicts-div").show();
    }
    if ($("#variables-table tbody tr").length > 0) {
        $("#variables-div").show();
    }
}
