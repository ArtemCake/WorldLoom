// frontend/src/js/features/rules/books/book-table-data.js

function tableCells(line) {
    const source = line.trim();
    const cells = [''];
    let escaped = false;
    let separators = 0;
    let trailingSeparator = false;

    for (const character of source) {
        const index = cells.length - 1;
        trailingSeparator = false;

        if (character === '|' && !escaped) {
            cells.push('');
            separators += 1;
            trailingSeparator = true;
        } else if (character === '|' && escaped) {
            cells[index] = `${cells[index].slice(0, -1)}|`;
        } else {
            cells[index] += character;
        }

        escaped = character === '\\' ? !escaped : false;
    }

    if (!separators) return null;
    if (source.startsWith('|')) cells.shift();
    if (trailingSeparator) cells.pop();

    return cells.length ? cells.map((cell) => cell.trim()) : null;
}

function columnAlignment(value) {
    if (value.startsWith(':') && value.endsWith(':')) return 'center';
    if (value.endsWith(':')) return 'right';
    if (value.startsWith(':')) return 'left';
    return null;
}

export function readBookTable(lines, start) {
    const first = lines[start];
    const second = lines[start + 1];

    if (typeof first !== 'string' || typeof second !== 'string') return null;

    const headers = tableCells(first);
    const divider = tableCells(second);

    if (!headers || !divider || headers.length !== divider.length) return null;
    if (!divider.every((cell) => /^:?-{3,}:?$/u.test(cell))) return null;

    const rows = [];
    let index = start + 2;

    while (index < lines.length && lines[index].trim()) {
        const cells = tableCells(lines[index]);
        if (!cells || cells.length !== headers.length) break;

        rows.push(cells);
        index += 1;
    }

    return {
        block: {
            type: 'table',
            headers,
            alignments: divider.map(columnAlignment),
            rows
        },
        nextIndex: index
    };
}
