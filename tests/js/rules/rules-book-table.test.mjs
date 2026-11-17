// tests/js/rules/rules-book-table.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { readBookTable } from '../../../frontend/src/js/features/rules/books/book-table-data.js';
import { readBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-data.js';
import { createBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-view.js';
import { createDraftProsePreview } from '../../../frontend/src/js/features/rules/draft/draft-prose-preview.js';

const TABLE = [
    '| Проверка | Сложность |',
    '| :--- | ---: |',
    '| Простая | 10 |',
    '| Сложная | 20 |'
].join('\n');

class TestNode extends EventTarget {
    constructor(tagName) {
        super();
        this.tagName = tagName;
        this.children = [];
        this.attributes = {};
        this.value = '';
        this.open = false;
    }

    set textContent(value) {
        this.value = String(value);
        this.children = [];
    }

    get textContent() {
        return this.value + this.children.map((child) => child.textContent).join('');
    }

    set innerHTML(value) {
        throw new Error(`HTML-вставка запрещена: ${value}`);
    }

    append(...nodes) {
        this.children.push(...nodes);
    }

    replaceChildren(...nodes) {
        this.value = '';
        this.children = [...nodes];
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    remove() {}
}

function testDocument() {
    const allowed = new Set([
        'div', 'p', 'br', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote',
        'pre', 'code', 'strong', 'em', 'details', 'summary',
        'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]);

    return {
        createElement(tag) {
            assert.ok(allowed.has(tag), `Неожиданный элемент: ${tag}`);
            return new TestNode(tag);
        },

        createTextNode(value) {
            const node = new TestNode('#text');
            node.textContent = value;
            return node;
        }
    };
}

function walk(node) {
    return [node, ...node.children.flatMap(walk)];
}

test('Таблица получает заголовки, строки и выравнивание', () => {
    const blocks = readBookProse(TABLE);

    assert.deepEqual(blocks, [{
        type: 'table',
        headers: ['Проверка', 'Сложность'],
        alignments: ['left', 'right'],
        rows: [['Простая', '10'], ['Сложная', '20']]
    }]);
});

test('Крайние черты необязательны, центрирование распознаётся', () => {
    const source = 'Название | Значение\n--- | :---:\nПроверка | 15';
    const [table] = readBookProse(source);

    assert.equal(table.type, 'table');
    assert.deepEqual(table.alignments, [null, 'center']);
    assert.deepEqual(table.rows, [['Проверка', '15']]);
});

test('Таблица может состоять только из заголовка и разделителя', () => {
    const [table] = readBookProse('| Параметр |\n| --- |');

    assert.equal(table.type, 'table');
    assert.deepEqual(table.headers, ['Параметр']);
    assert.deepEqual(table.rows, []);
});

test('Экранированная черта остаётся внутри ячейки', () => {
    const source = String.raw`| Выражение | Значение |
| --- | --- |
| A \| B | 2 |`;
    const [table] = readBookProse(source);

    assert.deepEqual(table.rows, [['A | B', '2']]);
});

test('Обычные обратные косые черты не удаляются', () => {
    const source = String.raw`| Путь | Значение |
| --- | --- |
| C:\rules | 1 |`;
    const [table] = readBookProse(source);

    assert.equal(table.rows[0][0], String.raw`C:\rules`);
});

test('Пустые ячейки не исчезают', () => {
    const source = '| A | B | C |\n| --- | --- | --- |\n| | 2 | |';
    const [table] = readBookProse(source);

    assert.deepEqual(table.rows, [['', '2', '']]);
});

test('Некорректный разделитель не превращает текст в таблицу', () => {
    for (const divider of ['| -- | --- |', '| --- |', '| текст | --- |']) {
        const source = `| A | B |\n${divider}\n| 1 | 2 |`;

        assert.deepEqual(readBookProse(source), [{ type: 'paragraph', text: source }]);
    }

    assert.equal(readBookTable([], 0), null);
});

test('Таблица отделяется от соседних абзацев без пустых строк', () => {
    const blocks = readBookProse(`До таблицы\n${TABLE}\nПосле таблицы`);

    assert.deepEqual(blocks.map((block) => block.type), ['paragraph', 'table', 'paragraph']);
    assert.equal(blocks[0].text, 'До таблицы');
    assert.equal(blocks[2].text, 'После таблицы');
});

test('Строки неправильной ширины не обрезаются и остаются текстом', () => {
    for (const line of ['| Только одна ячейка |', '| A | B | Лишняя ячейка |']) {
        const blocks = readBookProse(`${TABLE}\n${line}`);

        assert.equal(blocks[0].rows.length, 2);
        assert.deepEqual(blocks[1], { type: 'paragraph', text: line });
    }
});

test('Внутри блока кода таблица не разбирается', () => {
    const source = ['```text', TABLE, '```'].join('\n');

    assert.deepEqual(readBookProse(source), [{ type: 'code', text: TABLE }]);
});

test('Входная строка и массив строк не изменяются', () => {
    const source = TABLE.replace(/\n/gu, '\r\n');
    const lines = TABLE.split('\n');
    const before = [...lines];

    readBookProse(source);
    readBookTable(lines, 0);

    assert.ok(source.includes('\r\n'));
    assert.deepEqual(lines, before);
});

test('Таблица создаёт шапку, тело и заголовки колонок', () => {
    const view = createBookProse(testDocument(), TABLE);
    const nodes = walk(view);
    const wrapper = view.children[0];
    const table = nodes.find((node) => node.tagName === 'table');
    const headers = nodes.filter((node) => node.tagName === 'th');

    assert.equal(wrapper.className, 'rules-catalog__table-scroll');
    assert.equal(wrapper.attributes.role, 'region');
    assert.equal(wrapper.attributes.tabindex, '0');
    assert.ok(wrapper.attributes['aria-label']);
    assert.deepEqual(table.children.map((node) => node.tagName), ['thead', 'tbody']);
    assert.equal(table.children[1].children.length, 2);
    assert.ok(headers.every((node) => node.attributes.scope === 'col'));
    assert.equal(headers[1].className, 'rules-catalog__cell--right');
});

test('Оформление внутри ячеек использует общий безопасный обработчик', () => {
    const source = '| Поле | Бросок |\n| --- | --- |\n| **Сила** | `1d20` |';
    const nodes = walk(createBookProse(testDocument(), source));

    assert.ok(nodes.some((node) => node.tagName === 'strong' && node.textContent === 'Сила'));
    assert.ok(nodes.some((node) => node.tagName === 'code' && node.textContent === '1d20'));
});

test('HTML и опасные адреса в ячейках не создают исполняемых элементов', () => {
    const payload = '<img src=x onerror=alert(1)>';
    const source = `| Поле | Значение |\n| --- | --- |\n| ${payload} | [ссылка](javascript:alert(2)) |`;
    const view = createBookProse(testDocument(), source);
    const forbidden = new Set(['img', 'script', 'iframe', 'a', 'svg']);

    assert.equal(walk(view).some((node) => forbidden.has(node.tagName)), false);
    assert.ok(view.textContent.includes(payload));
    assert.ok(view.textContent.includes('javascript:alert(2)'));
});

test('Локальный предпросмотр показывает таблицу тем же обработчиком', () => {
    const preview = createDraftProsePreview({ document: testDocument() });

    preview.root.open = true;
    preview.render(TABLE);

    assert.ok(walk(preview.root).some((node) => node.tagName === 'table'));

    preview.render('Обычный текст');

    assert.equal(walk(preview.root).some((node) => node.tagName === 'table'), false);
    assert.ok(preview.root.textContent.includes('Обычный текст'));
    preview.dispose();
});
