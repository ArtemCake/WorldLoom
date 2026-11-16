// tests/js/rules/rules-book-prose.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { readBookInline, readBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-data.js';
import { createBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-view.js';
import { createDraftProsePreview } from '../../../frontend/src/js/features/rules/draft/draft-prose-preview.js';

class TestNode extends EventTarget {
    constructor(tagName) {
        super();
        this.tagName = tagName;
        this.children = [];
        this.attributes = {};
        this.open = false;
        this.removed = false;
        this.value = '';
    }

    set textContent(value) {
        this.value = String(value);
        this.children = [];
    }

    get textContent() {
        return this.value + this.children.map((child) => child.textContent).join('');
    }

    set innerHTML(value) {
        throw new Error(`Небезопасная HTML-вставка: ${value}`);
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

    remove() {
        this.removed = true;
    }
}

function testDocument() {
    const allowed = new Set([
        'div', 'p', 'br', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote',
        'pre', 'code', 'strong', 'em', 'details', 'summary'
    ]);

    return {
        createElement(tag) {
            assert.ok(allowed.has(tag), `Неожиданный тег: ${tag}`);
            return new TestNode(tag);
        },

        createTextNode(value) {
            const node = new TestNode('#text');
            node.textContent = value;
            return node;
        }
    };
}

function allNodes(node) {
    return [node, ...node.children.flatMap(allNodes)];
}

test('Абзацы и переносы строк разбираются без изменения исходной строки', () => {
    const source = 'Первая строка\r\nВторая строка\r\n\r\nСледующий абзац';

    assert.deepEqual(readBookProse(source), [
        { type: 'paragraph', text: 'Первая строка\nВторая строка' },
        { type: 'paragraph', text: 'Следующий абзац' }
    ]);
    assert.ok(source.includes('\r\n'));
});

test('Заголовки, цитаты и оба вида списков различаются', () => {
    const source = '# Проверки\n- Сила\n- Ловкость\n3. Бросок\n4. Результат\n> Первая строка\n> Вторая строка';
    const blocks = readBookProse(source);

    assert.deepEqual(blocks[0], { type: 'heading', level: 1, text: 'Проверки' });
    assert.deepEqual(blocks[1], { type: 'list', ordered: false, start: null, items: ['Сила', 'Ловкость'] });
    assert.deepEqual(blocks[2], { type: 'list', ordered: true, start: 3, items: ['Бросок', 'Результат'] });
    assert.deepEqual(blocks[3], { type: 'quote', text: 'Первая строка\nВторая строка' });
});

test('Простое строчное оформление не разбирает HTML', () => {
    assert.deepEqual(readBookInline('**Важно** *пример* `1d20` <img src=x>'), [
        { type: 'strong', text: 'Важно' },
        { type: 'text', text: ' ' },
        { type: 'em', text: 'пример' },
        { type: 'text', text: ' ' },
        { type: 'code', text: '1d20' },
        { type: 'text', text: ' <img src=x>' }
    ]);
});

test('Внутри блока кода маркеры не интерпретируются', () => {
    const source = ['```text', '# Заголовок', '**Выделение**', '', '<script>test()</script>', '```'].join('\n');
    const blocks = readBookProse(source);

    assert.deepEqual(blocks, [{
        type: 'code',
        text: '# Заголовок\n**Выделение**\n\n<script>test()</script>'
    }]);
});

test('Незакрытый блок кода отображает введённое содержание', () => {
    assert.deepEqual(readBookProse('```\nПервая строка\nВторая строка'), [
        { type: 'code', text: 'Первая строка\nВторая строка' }
    ]);
});

test('Неподдерживаемая разметка и незавершённые маркеры остаются текстом', () => {
    const source = '| Поле | Значение |\n![рисунок](image.png)\n**Незавершённое';

    assert.deepEqual(readBookProse(source), [{ type: 'paragraph', text: source }]);
    assert.deepEqual(readBookInline('**Незавершённое'), [{ type: 'text', text: '**Незавершённое' }]);
});

test('Нестрочные значения отклоняются', () => {
    for (const value of [null, undefined, 12, {}, []]) {
        assert.throws(() => readBookProse(value), TypeError);
        assert.throws(() => readBookInline(value), TypeError);
    }
});

test('Вывод создаёт структурные элементы и сохраняет начальный номер списка', () => {
    const document = testDocument();
    const rendered = createBookProse(document, '# Проверки\n\n3. **Сила**\n4. *Ловкость*\n\nСтрока\nПеренос');

    assert.deepEqual(rendered.children.map((node) => node.tagName), ['h4', 'ol', 'p']);
    assert.equal(rendered.children[1].attributes.start, '3');
    assert.equal(rendered.children[1].children[0].children[0].tagName, 'strong');
    assert.equal(rendered.children[1].children[1].children[0].tagName, 'em');
    assert.equal(rendered.children[2].children[1].tagName, 'br');
});

test('HTML, изображения и опасные адреса остаются обычным текстом', () => {
    const source = '<img src=x onerror=alert(1)>\n<script>alert(2)</script>\n[ссылка](javascript:alert(3))';
    const rendered = createBookProse(testDocument(), source);
    const nodes = allNodes(rendered);

    assert.equal(nodes.some((node) => ['img', 'script', 'a', 'iframe'].includes(node.tagName)), false);
    assert.ok(rendered.textContent.includes('<img src=x onerror=alert(1)>'));
    assert.ok(rendered.textContent.includes('<script>alert(2)</script>'));
    assert.ok(rendered.textContent.includes('javascript:alert(3)'));
});

test('Глубокие заголовки не выходят за шестой уровень', () => {
    const rendered = createBookProse(testDocument(), '###### Подробности');

    assert.equal(rendered.children[0].tagName, 'h6');
});

test('Свёрнутый предпросмотр отображает последнее значение после раскрытия', () => {
    const preview = createDraftProsePreview({ document: testDocument() });
    const content = preview.root.children[2];

    preview.render('Первое значение');
    preview.render('Второе значение');
    assert.equal(content.children.length, 0);

    preview.root.open = true;
    preview.root.dispatchEvent(new Event('toggle'));

    assert.equal(content.textContent, 'Второе значение');
    preview.dispose();
});

test('Открытый предпросмотр обновляется без замены неизменившегося содержания', () => {
    const preview = createDraftProsePreview({ document: testDocument() });
    const content = preview.root.children[2];

    preview.root.open = true;
    preview.render('Первый текст');
    const first = content.children[0];

    preview.render('Первый текст');
    assert.equal(content.children[0], first);

    preview.render('Другой текст');
    assert.notEqual(content.children[0], first);
    assert.equal(content.textContent, 'Другой текст');
    preview.dispose();
});

test('Очистка убирает текст предыдущего раздела и закрывает предпросмотр', () => {
    const preview = createDraftProsePreview({ document: testDocument() });
    const content = preview.root.children[2];

    preview.root.open = true;
    preview.render('Предыдущий раздел');
    preview.clear();

    assert.equal(preview.root.open, false);
    assert.equal(content.children.length, 0);

    preview.render('Новый раздел');
    preview.root.open = true;
    preview.root.dispatchEvent(new Event('toggle'));

    assert.equal(content.textContent, 'Новый раздел');
    preview.dispose();
});

test('Пустое содержание получает пояснение, уничтоженная панель больше не обновляется', () => {
    const preview = createDraftProsePreview({ document: testDocument() });
    const content = preview.root.children[2];

    preview.root.open = true;
    preview.render('   ');
    assert.equal(content.textContent, 'Текст пока не добавлен.');

    preview.dispose();
    preview.root.open = true;
    preview.render('Не показывать');
    preview.root.dispatchEvent(new Event('toggle'));

    assert.equal(preview.root.removed, true);
    assert.equal(content.children.length, 0);
});
