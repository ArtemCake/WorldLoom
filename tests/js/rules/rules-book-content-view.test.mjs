// tests/js/rules/rules-book-content-view.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { createBookContent } from '../../../frontend/src/js/features/rules/books/book-content-view.js';
import { createBookSources } from '../../../frontend/src/js/features/rules/books/book-sources-view.js';
import { createBookProse } from '../../../frontend/src/js/features/rules/books/book-prose-view.js';

class TestNode {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.attributes = {};
        this.value = '';
        this.parentNode = null;
    }

    set textContent(value) {
        this.value = String(value);
        this.children = [];
    }

    get textContent() {
        return this.value + this.children.map((child) => child.textContent).join('');
    }

    set innerHTML(value) {
        throw new Error(`Запрещённая HTML-вставка: ${value}`);
    }

    append(...nodes) {
        for (const node of nodes) {
            if (node.parentNode) throw new Error('Тест ожидает добавление нового узла.');
            node.parentNode = this;
            this.children.push(node);
        }
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
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

function walk(node) {
    return [node, ...node.children.flatMap(walk)];
}

function section(key, parentKey, depth, values = {}) {
    return { key, parentKey, depth, title: key, body: '', sources: [], ...values };
}

function book(values = {}) {
    return {
        title: 'Книга правил',
        version: 2,
        introduction: 'Введение',
        sources: [],
        sections: [
            section('chapter', null, 0, { title: 'Проверки' }),
            section('ability', 'chapter', 1, { title: 'Характеристики', body: '**Бросок**' }),
            section('combat', null, 0, { title: 'Бой', body: 'Порядок хода' })
        ],
        ...values
    };
}

function isSection(node) {
    return node.tagName === 'section';
}

test('Раздел находится внутри своей главы, соседняя глава остаётся на верхнем уровне', () => {
    const view = createBookContent(testDocument(), book());
    const roots = view.children.filter(isSection);

    assert.equal(roots.length, 2);
    assert.equal(roots[0].children[0].textContent, 'Проверки');
    assert.equal(roots[1].children[0].textContent, 'Бой');

    const nested = roots[0].children.filter(isSection);

    assert.equal(nested.length, 1);
    assert.equal(nested[0].children[0].textContent, 'Характеристики');
    assert.equal(roots[1].children.filter(isSection).length, 0);
});

test('В оглавлении нет пустых вложенных списков', () => {
    const view = createBookContent(testDocument(), book());
    const navigation = view.children.find((node) => node.tagName === 'nav');
    const lists = walk(navigation).filter((node) => node.tagName === 'ul');

    assert.equal(lists.length, 2);
    assert.ok(lists.every((node) => node.children.length > 0));
});

test('Каждая внутренняя ссылка ведёт к существующему уникальному заголовку', () => {
    const view = createBookContent(testDocument(), book());
    const nodes = walk(view);
    const identified = nodes.filter((node) => node.id);
    const targets = new Map(identified.map((node) => [node.id, node]));
    const links = nodes.filter((node) => node.tagName === 'a');

    assert.equal(targets.size, identified.length);
    assert.equal(links.length, 6);

    for (const link of links) {
        assert.ok(link.href.startsWith('#'));
        const target = targets.get(link.href.slice(1));

        assert.ok(target);
        assert.equal(target.attributes.tabindex, '-1');
        assert.equal(link.attributes['hx-boost'], 'false');
    }
});

test('Два экземпляра книги не используют одинаковые идентификаторы', () => {
    const document = testDocument();
    const first = createBookContent(document, book());
    const second = createBookContent(document, book());
    const firstIds = new Set(walk(first).map((node) => node.id).filter(Boolean));
    const secondIds = walk(second).map((node) => node.id).filter(Boolean);

    assert.ok(secondIds.every((id) => !firstIds.has(id)));
});

test('Уровни заголовков разделов учитывают вложенность', () => {
    const view = createBookContent(testDocument(), book());
    const sections = walk(view).filter(isSection);

    assert.deepEqual(sections.map((node) => node.children[0].tagName), ['h3', 'h4', 'h3']);
});

test('Заголовки содержания учитывают переданный уровень и ограничиваются шестым', () => {
    const view = createBookProse(testDocument(), '# Первый\n###### Глубокий', { headingLevel: 5 });

    assert.deepEqual(view.children.map((node) => node.tagName), ['h5', 'h6']);
    assert.equal(createBookProse(testDocument(), '# По умолчанию').children[0].tagName, 'h4');

    for (const level of [0, 7, 2.5, '4', null]) {
        assert.throws(() => createBookProse(testDocument(), '# Текст', { headingLevel: level }), TypeError);
    }
});

test('Источники книги и раздела отображаются отдельно', () => {
    const data = book({ sources: [{ title: 'Общий источник' }] });
    data.sections[1].sources = [{ title: 'Источник характеристики' }];

    const view = createBookContent(testDocument(), data);
    const common = view.children.find((node) => node.tagName === 'details');
    const nested = walk(view).find((node) => isSection(node) && node.children[0].textContent === 'Характеристики');
    const local = nested.children.find((node) => node.tagName === 'details');

    assert.equal(common.children[0].textContent, 'Источники книги и условия использования');
    assert.equal(local.children[0].textContent, 'Источники раздела и условия использования');
    assert.ok(common.textContent.includes('Общий источник'));
    assert.ok(local.textContent.includes('Источник характеристики'));
    assert.equal(common.textContent.includes('Источник характеристики'), false);
});

test('Все текстовые поля источника и безопасные ссылки сохраняются', () => {
    const source = {
        title: 'Книга-источник',
        publisher: 'Издатель',
        locator: 'Глава 3',
        license_name: 'Условия использования',
        attribution: 'Указание авторства',
        url: 'https://example.test/source',
        license_url: 'http://example.test/license'
    };
    const view = createBookSources(testDocument(), [source]);
    const links = walk(view).filter((node) => node.tagName === 'a');

    for (const key of ['title', 'publisher', 'locator', 'license_name', 'attribution']) {
        assert.ok(view.textContent.includes(source[key]));
    }

    assert.deepEqual(links.map((node) => node.href), [source.url, source.license_url]);

    for (const link of links) {
        assert.equal(link.target, '_blank');
        assert.equal(link.rel, 'noopener noreferrer');
        assert.equal(link.attributes['hx-boost'], 'false');
    }
});

test('Небезопасные и некорректные адреса не становятся ссылками', () => {
    const values = ['javascript:alert(1)', 'data:text/html,test', '/relative', 'не адрес'];

    for (const url of values) {
        const view = createBookSources(testDocument(), [{ title: 'Источник', url }]);

        assert.equal(walk(view).some((node) => node.tagName === 'a'), false);
        assert.ok(view.textContent.includes('Источник'));
    }

    assert.equal(createBookSources(testDocument(), []), null);
});

test('Разметка HTML в названии, тексте и атрибуции остаётся текстом', () => {
    const payload = '<img src=x onerror=alert(1)>';
    const data = book({
        title: payload,
        introduction: payload,
        sources: [{ title: payload, attribution: '<script>alert(2)</script>' }]
    });
    data.sections[1].body = payload;

    const view = createBookContent(testDocument(), data);
    const nodes = walk(view);

    assert.equal(nodes.some((node) => ['img', 'script', 'iframe'].includes(node.tagName)), false);
    assert.ok(view.textContent.includes(payload));
    assert.ok(view.textContent.includes('<script>alert(2)</script>'));
});

test('Пустая структура получает пояснение без пустого списка', () => {
    const view = createBookContent(testDocument(), book({ sections: [] }));
    const navigation = view.children.find((node) => node.tagName === 'nav');

    assert.ok(navigation.textContent.includes('Оглавление пока пустое.'));
    assert.equal(walk(navigation).some((node) => node.tagName === 'ul'), false);
});

test('Вывод не изменяет переданную модель книги', () => {
    const data = book();
    const before = structuredClone(data);

    createBookContent(testDocument(), data);

    assert.deepEqual(data, before);
});

test('Отсутствующий родитель не маскируется выводом раздела в корне', () => {
    const data = book({ sections: [section('orphan', 'missing', 1)] });

    assert.throws(() => createBookContent(testDocument(), data), TypeError);
});
