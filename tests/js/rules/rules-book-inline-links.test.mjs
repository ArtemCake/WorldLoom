// tests/js/rules/rules-book-inline-links.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { readBookInline } from '../../../frontend/src/js/features/rules/books/book-inline-data.js';
import { readBookInline as readPublicInline } from '../../../frontend/src/js/features/rules/books/book-prose-data.js';
import { createBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-view.js';
import { createDraftProsePreview } from '../../../frontend/src/js/features/rules/draft/draft-prose-preview.js';

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
        'pre', 'code', 'strong', 'em', 'details', 'summary', 'a',
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

function links(node) {
    return walk(node).filter((item) => item.tagName === 'a');
}

test('Абсолютные HTTP и HTTPS превращаются в ссылки', () => {
    for (const href of ['http://example.org/rules', 'https://example.org/rules', 'HTTPS://example.org/rules']) {
        assert.deepEqual(readBookInline(`[Правила](${href})`), [
            { type: 'link', text: 'Правила', href }
        ]);
    }
});

test('Публичный экспорт использует новый обработчик', () => {
    const source = 'Текст [Источник](https://example.org/rules)';

    assert.deepEqual(readPublicInline(source), readBookInline(source));
});

test('Текст вокруг ссылки, запрос и фрагмент сохраняются', () => {
    const href = 'https://example.org/rules?edition=2014&lang=ru#checks';

    assert.deepEqual(readBookInline(`До [Проверки](${href}) после`), [
        { type: 'text', text: 'До ' },
        { type: 'link', text: 'Проверки', href },
        { type: 'text', text: ' после' }
    ]);
});

test('Прежнее жирное, курсивное оформление и код сохраняются', () => {
    assert.deepEqual(readBookInline('**Важно** *пример* `1d20`'), [
        { type: 'strong', text: 'Важно' },
        { type: 'text', text: ' ' },
        { type: 'em', text: 'пример' },
        { type: 'text', text: ' ' },
        { type: 'code', text: '1d20' }
    ]);
});

test('Несколько ссылок и соседнее оформление разбираются независимо', () => {
    const source = '**Важно** [Один](https://example.org/one) и [Два](https://example.org/two)';
    const parts = readBookInline(source);

    assert.equal(parts[0].type, 'strong');
    assert.deepEqual(parts.filter((part) => part.type === 'link').map((part) => part.text), ['Один', 'Два']);
});

test('Опасные, относительные и содержащие учётные данные адреса остаются текстом', () => {
    const addresses = [
        'javascript:alert',
        'JaVaScRiPt:alert',
        'data:text/html,test',
        'vbscript:msgbox',
        'file:///tmp/rules',
        'blob:https://example.org/id',
        '//example.org/rules',
        '/rules/catalog',
        '#checks',
        'https://user:password@example.org/rules',
        'https://',
        'https://example.org/\u0000test',
        'https://example.org/"test"',
        String.raw`https://example.org\test`
    ];

    for (const address of addresses) {
        const source = `[Источник](${address})`;
        const parts = readBookInline(source);

        assert.equal(parts.some((part) => part.type === 'link'), false, address);
        assert.equal(parts.map((part) => part.text).join(''), source);
    }
});

test('Пробелы и управляющие символы в адресе не допускаются', () => {
    for (const address of ['https://example.org/a b', 'https://example.org/a\tb', 'https://example.org/a\nb']) {
        const source = `[Источник](${address})`;
        const parts = readBookInline(source);

        assert.equal(parts.some((part) => part.type === 'link'), false);
        assert.equal(parts.map((part) => part.text).join(''), source);
    }
});

test('Внутри строчного кода ссылки не активируются', () => {
    const source = '`[Источник](https://example.org/rules)`';

    assert.deepEqual(readBookInline(source), [
        { type: 'code', text: '[Источник](https://example.org/rules)' }
    ]);
});

test('Изображения, пустые подписи и незавершённая ссылка остаются текстом', () => {
    const values = [
        '![Рисунок](https://example.org/image.png)',
        '[ ](https://example.org/rules)',
        '[Источник](https://example.org/rules'
    ];

    for (const source of values) {
        const parts = readBookInline(source);

        assert.equal(parts.some((part) => part.type === 'link'), false);
        assert.equal(parts.map((part) => part.text).join(''), source);
    }
});

test('Закодированные скобки в адресе поддерживаются', () => {
    const href = 'https://example.org/rules_%28base%29';

    assert.deepEqual(readBookInline(`[Правила](${href})`), [
        { type: 'link', text: 'Правила', href }
    ]);
});

test('Нестрочные значения отклоняются', () => {
    for (const value of [null, undefined, 12, {}, []]) {
        assert.throws(() => readBookInline(value), TypeError);
    }
});

test('Ссылка получает безопасные атрибуты и отключает перехват перехода', () => {
    const view = createBookProse(testDocument(), '[Правила](https://example.org/rules)');
    const [link] = links(view);

    assert.equal(links(view).length, 1);
    assert.equal(link.textContent, 'Правила');
    assert.deepEqual(link.attributes, {
        href: 'https://example.org/rules',
        target: '_blank',
        rel: 'noopener noreferrer',
        'hx-boost': 'false'
    });
});

test('HTML в подписи не создаёт HTML-элементы', () => {
    const payload = '<img src=x onerror=alert>';
    const view = createBookProse(testDocument(), `[${payload}](https://example.org/rules)`);

    assert.equal(links(view).length, 1);
    assert.equal(links(view)[0].textContent, payload);
    assert.equal(walk(view).some((node) => ['img', 'script', 'iframe'].includes(node.tagName)), false);
});

test('Опасный адрес с вызовом функции не становится ссылкой', () => {
    const source = '[Источник](javascript:alert(1))';
    const view = createBookProse(testDocument(), source);

    assert.equal(links(view).length, 0);
    assert.equal(view.textContent, source);
});

test('В блоке кода ссылка остаётся буквальным текстом', () => {
    const source = ['```text', '[Источник](https://example.org/rules)', '```'].join('\n');
    const view = createBookProse(testDocument(), source);

    assert.equal(links(view).length, 0);
    assert.equal(view.children[0].tagName, 'pre');
    assert.equal(view.textContent, '[Источник](https://example.org/rules)');
});

test('Таблица сохраняется и отображает ссылку внутри ячейки', () => {
    const source = [
        '| Раздел | Источник |',
        '| --- | --- |',
        '| **Проверки** | [Описание](https://example.org/checks) |'
    ].join('\n');
    const view = createBookProse(testDocument(), source);
    const nodes = walk(view);

    assert.ok(nodes.some((node) => node.tagName === 'table'));
    assert.ok(nodes.some((node) => node.tagName === 'strong' && node.textContent === 'Проверки'));
    assert.equal(links(view).length, 1);
    assert.equal(links(view)[0].attributes.href, 'https://example.org/checks');
});

test('Заголовок, список и цитата используют тот же обработчик ссылок', () => {
    const source = [
        '# [Основы](https://example.org/basics)',
        '',
        '- [Проверки](https://example.org/checks)',
        '',
        '> [Пример](https://example.org/example)'
    ].join('\n');
    const view = createBookProse(testDocument(), source);

    assert.deepEqual(view.children.map((node) => node.tagName), ['h4', 'ul', 'blockquote']);
    assert.equal(links(view).length, 3);
});

test('Локальный предпросмотр применяет те же ограничения', () => {
    const preview = createDraftProsePreview({ document: testDocument() });

    preview.root.open = true;
    preview.render('[Источник](https://example.org/rules)');

    assert.equal(links(preview.root).length, 1);

    preview.render('[Источник](javascript:alert(1))');

    assert.equal(links(preview.root).length, 0);
    assert.ok(preview.root.textContent.includes('javascript:alert(1)'));
    preview.dispose();
});
