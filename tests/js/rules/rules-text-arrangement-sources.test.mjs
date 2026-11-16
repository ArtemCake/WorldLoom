// tests/js/rules/rules-text-arrangement-sources.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { applyBookTextCommand, applyBookTextSourceCommand } from '../../../frontend/src/js/features/rules/draft/draft-text-data.js';
import { validateBookToc } from '../../../frontend/src/js/features/rules/draft/draft-toc-data.js';
import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';

const BOOK = randomUUID();
const DRAFT = randomUUID();
const VERSION = randomUUID();

function own(key = 'own', parent = 'first', position = 5) {
    return {
        kind: 'text',
        key,
        parent_key: parent,
        position,
        title: 'Подпись в оглавлении',
        content: {
            schema_version: 1,
            title: 'Проверки',
            summary: 'Описание',
            body: 'Авторский текст.',
            language: 'ru',
            edition_key: null,
            audience: 'gm',
            rule_kind: 'homebrew',
            sources: [{ title: 'Книга', publisher: 'Издатель', locator: 'Глава 2' }]
        }
    };
}

function toc() {
    return [
        { kind: 'chapter', key: 'first', parent_key: null, position: 0, title: 'Первая' },
        { kind: 'chapter', key: 'second', parent_key: null, position: 1, title: 'Вторая' },
        own(),
        {
            kind: 'article',
            key: 'external',
            parent_key: 'first',
            position: 12,
            title: null,
            article_version_id: VERSION
        },
        own('last', 'first', 30)
    ];
}

function item(nodes, key = 'own') {
    return nodes.find((node) => node.key === key);
}

function sourceInput(nodes, field, value, index = 0) {
    return applyBookTextSourceCommand(nodes, { type: 'input', key: 'own', index, field, value });
}

function draft() {
    return {
        id: DRAFT,
        book_id: BOOK,
        revision: 1,
        content_json: {
            schema_version: 2,
            title: 'Книга правил',
            summary: '',
            introduction: '',
            language: 'ru',
            edition_key: null,
            category: 'rules',
            audience: 'both',
            sources: [{ title: 'Общий источник книги' }],
            toc: toc()
        }
    };
}

function setup(overrides = {}) {
    const source = draft();
    const calls = [];
    const api = {
        async saveWorkingDraft(bookId, payload) {
            calls.push({ bookId, payload: structuredClone(payload) });
            return {
                ...structuredClone(source),
                revision: payload.expected_revision + 1,
                content_json: structuredClone(payload.content)
            };
        },

        async getWorkingEditor() {
            throw new Error('Не используется в этом тесте');
        },

        ...overrides
    };
    const workingState = {
        book: { id: BOOK },
        draft: structuredClone(source),
        latest_publication: null,
        has_unpublished_changes: true
    };
    const editor = createBookDraftEditor({ draft: source, workingState, api });

    return { source, calls, editor };
}

test('Перемещение меняет позиции текста и соседнего внешнего материала', () => {
    const source = toc();
    const before = structuredClone(source);
    const result = applyBookTextCommand(source, { type: 'move', key: 'own', delta: 1 });

    assert.equal(item(result).position, 12);
    assert.equal(item(result, 'external').position, 5);
    assert.deepEqual(item(result).content, item(source).content);
    assert.equal(item(result).title, item(source).title);
    assert.deepEqual(source, before);

    const restored = applyBookTextCommand(result, { type: 'move', key: 'own', delta: -1 });
    assert.deepEqual(restored, before);
});

test('Перемещение за границу уровня ничего не меняет', () => {
    const source = toc();

    assert.deepEqual(applyBookTextCommand(source, { type: 'move', key: 'own', delta: -1 }), source);
    assert.deepEqual(applyBookTextCommand(source, { type: 'move', key: 'last', delta: 1 }), source);
});

test('Собственный текст меняется местами и с соседней главой', () => {
    const source = toc();
    source.push({ kind: 'chapter', key: 'nested', parent_key: 'first', position: 40, title: 'Вложенная' });

    const result = applyBookTextCommand(source, { type: 'move', key: 'last', delta: 1 });

    assert.equal(item(result, 'last').position, 40);
    assert.equal(item(result, 'nested').position, 30);
});

test('Перенос добавляет текст в конец выбранной главы, не меняя его содержание', () => {
    const source = toc();
    source.push(own('existing', 'second', 17));
    const result = applyBookTextCommand(source, { type: 'reparent', key: 'own', parent_key: 'second' });

    assert.equal(item(result).parent_key, 'second');
    assert.equal(item(result).position, 18);
    assert.deepEqual(item(result).content, item(source).content);
    assert.deepEqual(item(result, 'external'), item(source, 'external'));
    assert.equal(item(source).parent_key, 'first');
});

test('Можно перенести текст в корень и в пустую главу', () => {
    const root = applyBookTextCommand(toc(), { type: 'reparent', key: 'own', parent_key: null });

    assert.equal(item(root).parent_key, null);
    assert.equal(item(root).position, 2);

    const empty = applyBookTextCommand(root, { type: 'reparent', key: 'own', parent_key: 'second' });

    assert.equal(item(empty).parent_key, 'second');
    assert.equal(item(empty).position, 0);
});

test('Повторный выбор текущей главы не меняет порядок', () => {
    const source = toc();
    const result = applyBookTextCommand(source, { type: 'reparent', key: 'own', parent_key: 'first' });

    assert.deepEqual(result, source);
});

test('Недопустимые направления и родители отклоняются без изменения исходника', () => {
    const source = toc();
    const before = structuredClone(source);

    for (const parent of ['missing', 'external', 'own', undefined, 42]) {
        const command = { type: 'reparent', key: 'own', parent_key: parent };
        assert.throws(() => applyBookTextCommand(source, command), TypeError);
    }

    for (const delta of [0, 2, -2, '1', null]) {
        assert.throws(() => applyBookTextCommand(source, { type: 'move', key: 'own', delta }), TypeError);
    }

    assert.deepEqual(source, before);
});

test('Переполнение позиции отклоняется без частичного переноса', () => {
    const source = toc();
    source.push(own('existing', 'second', Number.MAX_SAFE_INTEGER));
    const before = structuredClone(source);
    const command = { type: 'reparent', key: 'own', parent_key: 'second' };

    assert.throws(() => applyBookTextCommand(source, command), TypeError);
    assert.deepEqual(source, before);
});

test('Источники добавляются и удаляются только у выбранного текста', () => {
    const source = toc();
    const added = applyBookTextSourceCommand(source, { type: 'add', key: 'own' });

    assert.equal(item(added).content.sources.length, 2);
    assert.equal(item(source).content.sources.length, 1);
    assert.deepEqual(item(added, 'last'), item(source, 'last'));

    const removed = applyBookTextSourceCommand(added, { type: 'remove', key: 'own', index: 1 });
    assert.deepEqual(removed, source);
});

test('Промежуточные значения источника сохраняются локально, но не проходят окончательную проверку', () => {
    const emptyTitle = sourceInput(toc(), 'title', '');

    assert.equal(item(emptyTitle).content.sources[0].title, '');
    assert.throws(() => validateBookToc(emptyTitle), TypeError);

    const invalidUrl = sourceInput(toc(), 'url', 'незавершённый адрес');

    assert.equal(item(invalidUrl).content.sources[0].url, 'незавершённый адрес');
    assert.throws(() => validateBookToc(invalidUrl), TypeError);

    const cleared = sourceInput(invalidUrl, 'url', '');
    assert.equal(item(cleared).content.sources[0].url, null);
    assert.doesNotThrow(() => validateBookToc(cleared));
});

test('Редактирование одного поля источника сохраняет остальные данные', () => {
    const source = toc();
    const result = sourceInput(source, 'locator', 'Глава 3');
    const expected = structuredClone(source);
    item(expected).content.sources[0].locator = 'Глава 3';

    assert.deepEqual(result, expected);
    assert.equal(item(source).content.sources[0].locator, 'Глава 2');
});

test('Произвольные поля и некорректные индексы источников запрещены', () => {
    const source = toc();

    for (const field of ['body', 'sources', '__proto__', 'unknown']) {
        assert.throws(() => sourceInput(source, field, 'Подмена'), TypeError);
    }

    for (const index of [-1, 1, 0.5, '0', null]) {
        assert.throws(() => sourceInput(source, 'title', 'Название', index), TypeError);
    }

    assert.throws(() => sourceInput(source, 'title', 42), TypeError);

    const command = { type: 'add', key: 'external' };
    assert.throws(() => applyBookTextSourceCommand(source, command), TypeError);
});

test('Ограничение количества источников не обрезает существующий список', () => {
    const source = toc();
    item(source).content.sources = Array.from({ length: 100 }, () => ({ title: 'Источник' }));
    const before = structuredClone(source);

    assert.throws(() => applyBookTextSourceCommand(source, { type: 'add', key: 'own' }), TypeError);
    assert.deepEqual(source, before);
});

test('Редактор сохраняет перемещение и источники одной записью с исходной ревизией', async () => {
    const { source, editor, calls } = setup();

    editor.text({ type: 'reparent', key: 'own', parent_key: 'second' });
    editor.textSource('own', { type: 'input', index: 0, field: 'locator', value: 'Глава 4' });

    assert.equal(editor.getState().dirty, true);
    assert.equal(editor.getState().needsGuard, true);

    const saved = await editor.save();
    const content = calls[0].payload.content;

    assert.equal(calls.length, 1);
    assert.equal(calls[0].payload.expected_revision, 1);
    assert.equal(saved.revision, 2);
    assert.equal(item(content.toc).parent_key, 'second');
    assert.equal(item(content.toc).content.sources[0].locator, 'Глава 4');
    assert.deepEqual(content.sources, source.content_json.sources);
    assert.equal(editor.getState().dirty, false);
});

test('Некорректный источник не отправляется, после исправления сохраняется', async () => {
    const { editor, calls } = setup();

    editor.textSource('own', { type: 'input', index: 0, field: 'title', value: '' });
    await assert.rejects(editor.save(), TypeError);

    assert.equal(calls.length, 0);
    assert.equal(editor.getState().blocked, false);
    assert.equal(item(editor.getState().toc).content.sources[0].title, '');

    editor.textSource('own', { type: 'input', index: 0, field: 'title', value: 'Исправленное название' });
    await editor.save();

    assert.equal(calls.length, 1);
    assert.equal(editor.getState().dirty, false);
});

test('Конфликт блокирует перемещение и изменение источников, оставляя локальные правки', async () => {
    const { editor } = setup({
        async saveWorkingDraft() {
            throw Object.assign(new Error('Конфликт'), { status: 409 });
        }
    });

    editor.textSource('own', { type: 'input', index: 0, field: 'locator', value: 'Локальная правка' });
    await editor.save();
    const before = editor.getState().toc;

    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.text({ type: 'move', key: 'own', delta: 1 }), false);
    assert.equal(editor.textSource('own', { type: 'remove', index: 0 }), false);
    assert.deepEqual(editor.getState().toc, before);
});

test('Во время записи изменение источников и перемещение недоступны', async () => {
    let finish;
    let submitted;
    const pending = new Promise((resolve) => { finish = resolve; });
    const { source, editor } = setup({
        saveWorkingDraft(bookId, payload) {
            submitted = structuredClone(payload);
            return pending;
        }
    });

    editor.textSource('own', { type: 'input', index: 0, field: 'locator', value: 'Глава 5' });
    const saving = editor.save();
    const before = editor.getState().toc;

    assert.equal(editor.text({ type: 'move', key: 'own', delta: 1 }), false);
    assert.equal(editor.textSource('own', { type: 'remove', index: 0 }), false);
    assert.deepEqual(editor.getState().toc, before);

    finish({ ...source, revision: 2, content_json: submitted.content });
    await saving;

    assert.equal(editor.getState().dirty, false);
});

test('После уничтожения редактора команды источников не применяются', () => {
    const { editor } = setup();
    const before = editor.getState().toc;

    editor.dispose();

    assert.equal(editor.textSource('own', { type: 'remove', index: 0 }), false);
    assert.deepEqual(editor.getState().toc, before);
});
