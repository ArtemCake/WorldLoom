// tests/js/rules/rules-book-content-navigation.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { createBookLocalLink } from '../../../frontend/src/js/features/rules/books/book-content-navigation.js';
import { createBookContent } from '../../../frontend/src/js/features/rules/books/book-content-view.js';

class TestNode {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.attributes = {};
        this.value = '';
        this.id = '';
        this.isConnected = true;
        this.calls = [];
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

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    focus(options) {
        this.calls.push({ method: 'focus', options });
    }

    scrollIntoView(options) {
        this.calls.push({ method: 'scrollIntoView', options });
    }
}

function testDocument() {
    return {
        createElement(tag) {
            return new TestNode(tag);
        },

        createTextNode(value) {
            const node = new TestNode('#text');
            node.textContent = value;
            return node;
        }
    };
}

function clickEvent(values = {}) {
    return {
        button: 0,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        altKey: false,
        defaultPrevented: false,

        preventDefault() {
            this.defaultPrevented = true;
        },

        ...values
    };
}

function walk(node) {
    return [node, ...node.children.flatMap(walk)];
}

function targetHeading(document, id = 'book-section') {
    const heading = document.createElement('h3');
    heading.id = id;
    return heading;
}

function book() {
    return {
        title: 'Тестовая книга',
        version: 1,
        introduction: '',
        sources: [],
        sections: [
            {
                key: 'basics',
                parentKey: null,
                depth: 0,
                title: 'Основы',
                body: '',
                sources: []
            },
            {
                key: 'checks',
                parentKey: 'basics',
                depth: 1,
                title: 'Проверки',
                body: 'Порядок проверки.',
                sources: []
            }
        ]
    };
}

test('Ссылка сохраняет настоящий якорный адрес и текст подписи', () => {
    const document = testDocument();
    const heading = targetHeading(document);
    const link = createBookLocalLink(document, heading, 'Перейти к разделу');

    assert.equal(link.tagName, 'a');
    assert.equal(link.href, '#book-section');
    assert.equal(link.textContent, 'Перейти к разделу');
    assert.equal(link.attributes['hx-boost'], 'false');
});

test('Обычный переход переносит фокус и прокручивает к заголовку', () => {
    const document = testDocument();
    const heading = targetHeading(document);
    const link = createBookLocalLink(document, heading, 'Раздел');
    const event = clickEvent();

    link.onclick(event);

    assert.equal(event.defaultPrevented, true);
    assert.deepEqual(heading.calls, [
        { method: 'focus', options: { preventScroll: true } },
        {
            method: 'scrollIntoView',
            options: { block: 'start', inline: 'nearest', behavior: 'auto' }
        }
    ]);
});

test('Модификаторы и неосновная кнопка не перехватываются', () => {
    const variants = [
        { ctrlKey: true },
        { metaKey: true },
        { shiftKey: true },
        { altKey: true },
        { button: 1 },
        { button: 2 }
    ];

    for (const values of variants) {
        const document = testDocument();
        const heading = targetHeading(document);
        const link = createBookLocalLink(document, heading, 'Раздел');
        const event = clickEvent(values);

        link.onclick(event);

        assert.equal(event.defaultPrevented, false);
        assert.deepEqual(heading.calls, []);
    }
});

test('Уже отменённое действие не запускает другой переход', () => {
    const document = testDocument();
    const heading = targetHeading(document);
    const link = createBookLocalLink(document, heading, 'Раздел');

    link.onclick(clickEvent({ defaultPrevented: true }));

    assert.deepEqual(heading.calls, []);
});

test('Удалённый из документа заголовок не получает фокус', () => {
    const document = testDocument();
    const heading = targetHeading(document);
    const link = createBookLocalLink(document, heading, 'Раздел');
    const event = clickEvent();

    heading.isConnected = false;
    link.onclick(event);

    assert.equal(event.defaultPrevented, false);
    assert.deepEqual(heading.calls, []);
});

test('Заголовок без идентификатора отклоняется', () => {
    const document = testDocument();

    for (const heading of [null, {}, targetHeading(document, '')]) {
        assert.throws(() => createBookLocalLink(document, heading, 'Раздел'), TypeError);
    }
});

test('Подпись ссылки не превращается в HTML', () => {
    const document = testDocument();
    const heading = targetHeading(document);
    const payload = '<img src=x onerror=alert(1)>';
    const link = createBookLocalLink(document, heading, payload);

    assert.equal(link.textContent, payload);
    assert.equal(link.children.length, 0);
});

test('Оглавление и возврат используют заголовки текущего экземпляра книги', () => {
    const document = testDocument();
    const data = book();
    const before = structuredClone(data);
    const first = createBookContent(document, data);
    const second = createBookContent(document, data);
    const firstNodes = walk(first);
    const secondNodes = walk(second);
    const targets = new Map(firstNodes.filter((node) => node.id).map((node) => [node.id, node]));
    const links = firstNodes.filter((node) => node.tagName === 'a');

    assert.equal(links.length, 4);

    for (const link of links) {
        const heading = targets.get(link.href.slice(1));
        const event = clickEvent();

        assert.ok(heading);
        assert.equal(heading.attributes.tabindex, '-1');

        link.onclick(event);

        assert.equal(event.defaultPrevented, true);
        assert.equal(heading.calls.length, 2);
        heading.calls.length = 0;
    }

    assert.ok(secondNodes.every((node) => node.calls.length === 0));
    assert.deepEqual(data, before);
});

test('В полном предпросмотре используется та же навигация', () => {
    const document = testDocument();
    const view = createBookContent(document, book(), { mode: 'draft' });
    const nodes = walk(view);
    const navigation = nodes.find((node) => node.tagName === 'nav');
    const link = walk(navigation).find((node) => node.tagName === 'a');
    const heading = nodes.find((node) => node.id === link.href.slice(1));
    const event = clickEvent();

    link.onclick(event);

    assert.equal(event.defaultPrevented, true);
    assert.equal(heading.calls[0].method, 'focus');
    assert.ok(view.textContent.includes('Предпросмотр локального черновика'));
});
