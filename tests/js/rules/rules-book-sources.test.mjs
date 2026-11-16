// tests/js/rules/rules-book-sources.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { applyDraftSourceCommand } from '../../../frontend/src/js/features/rules/draft/draft-source-data.js';
import { readBookSources } from '../../../frontend/src/js/features/rules/draft/draft-toc-data.js';
import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';

const BOOK = randomUUID();
const DRAFT = randomUUID();

function draft(revision = 1) {
    return {
        id: DRAFT,
        book_id: BOOK,
        revision,
        content_json: {
            schema_version: 2,
            title: 'Книга',
            summary: '',
            introduction: '',
            language: 'ru',
            edition_key: null,
            category: 'rules',
            audience: 'both',
            sources: [{ title: 'Общий источник', locator: 'Глава 1' }],
            toc: [{
                kind: 'text',
                key: 'own',
                parent_key: null,
                position: 0,
                title: null,
                content: {
                    schema_version: 1,
                    title: 'Проверки',
                    summary: '',
                    body: 'Содержание.',
                    language: 'ru',
                    edition_key: null,
                    audience: 'gm',
                    rule_kind: 'homebrew',
                    sources: [{ title: 'Источник собственного текста' }]
                }
            }]
        }
    };
}

function setup(overrides = {}) {
    const original = draft();
    const calls = [];
    let stored = structuredClone(original);
    let latest = null;

    function opened() {
        return {
            book: { id: BOOK },
            draft: structuredClone(stored),
            latest_publication: structuredClone(latest),
            has_unpublished_changes: latest === null
        };
    }

    const api = {
        async saveWorkingDraft(bookId, payload) {
            calls.push({ bookId, payload: structuredClone(payload) });
            stored = {
                ...stored,
                revision: payload.expected_revision + 1,
                content_json: structuredClone(payload.content)
            };
            return structuredClone(stored);
        },

        async getWorkingEditor() {
            return opened();
        },

        async publishWorkingDraft(bookId, payload) {
            assert.equal(bookId, BOOK);
            assert.equal(payload.expected_revision, stored.revision);

            const content = structuredClone(stored.content_json);
            content.schema_version = 1;
            content.toc = content.toc.map((node) => {
                if (node.kind !== 'text') return node;

                const result = { ...node, kind: 'article', article_version_id: randomUUID() };
                delete result.content;
                return result;
            });

            latest = {
                id: randomUUID(),
                book_id: BOOK,
                version_number: 1,
                source_draft_revision: stored.revision,
                content_json: content
            };

            stored.revision += 1;
            return { publication: structuredClone(latest), draft_revision: stored.revision };
        },

        ...overrides
    };

    const editor = createBookDraftEditor({ draft: original, workingState: opened(), api });
    return { original, editor, calls };
}

test('Общая команда не изменяет исходный список', () => {
    const sources = [{ title: 'Источник', locator: 'Глава 1' }];
    const command = { type: 'input', index: 0, field: 'locator', value: 'Глава 2' };
    const changed = applyDraftSourceCommand(sources, command);

    assert.equal(changed[0].locator, 'Глава 2');
    assert.equal(sources[0].locator, 'Глава 1');

    const added = applyDraftSourceCommand(changed, { type: 'add' });
    const removed = applyDraftSourceCommand(added, { type: 'remove', index: 1 });

    assert.deepEqual(removed, changed);
});

test('Проверка отклоняет незавершённое название и адрес, сохраняя локальный ввод', () => {
    const sources = [{ title: 'Источник' }];
    const blank = applyDraftSourceCommand(sources, { type: 'input', index: 0, field: 'title', value: '' });

    assert.equal(blank[0].title, '');
    assert.throws(() => readBookSources(blank), TypeError);

    const command = { type: 'input', index: 0, field: 'url', value: 'незавершённый адрес' };
    const invalid = applyDraftSourceCommand(sources, command);

    assert.equal(invalid[0].url, command.value);
    assert.throws(() => readBookSources(invalid), TypeError);

    const cleared = applyDraftSourceCommand(invalid, { ...command, value: '' });
    assert.equal(cleared[0].url, null);
    assert.doesNotThrow(() => readBookSources(cleared));
});

test('Неизвестные поля, неверные индексы и переполнение не меняют исходник', () => {
    const sources = [{ title: 'Источник' }];

    for (const field of ['body', '__proto__', 'unknown']) {
        const command = { type: 'input', index: 0, field, value: 'Подмена' };
        assert.throws(() => applyDraftSourceCommand(sources, command), TypeError);
    }

    for (const index of [-1, 1, '0', 0.5]) {
        assert.throws(() => applyDraftSourceCommand(sources, { type: 'remove', index }), TypeError);
    }

    const full = Array.from({ length: 100 }, () => ({ title: 'Источник' }));

    assert.throws(() => applyDraftSourceCommand(full, { type: 'add' }), TypeError);
    assert.equal(full.length, 100);
    assert.deepEqual(sources, [{ title: 'Источник' }]);
});

test('Изменение источника книги учитывается защитой навигации и не затрагивает раздел', async () => {
    const { original, editor, calls } = setup();

    assert.equal(editor.bookSource({ type: 'input', index: 0, field: 'locator', value: 'Глава 3' }), true);
    assert.equal(editor.getState().dirty, true);
    assert.equal(editor.getState().needsGuard, true);
    assert.equal(editor.getState().canPublish, false);

    await editor.save();
    const content = calls[0].payload.content;

    assert.equal(calls.length, 1);
    assert.equal(calls[0].payload.expected_revision, 1);
    assert.equal(content.sources[0].locator, 'Глава 3');
    assert.deepEqual(content.toc, original.content_json.toc);
    assert.equal(content.category, original.content_json.category);
    assert.equal(content.audience, original.content_json.audience);
    assert.equal(original.content_json.sources[0].locator, 'Глава 1');
    assert.equal(editor.getState().dirty, false);
});

test('Возврат исходного значения снимает признак изменений', () => {
    const { editor } = setup();

    editor.bookSource({ type: 'input', index: 0, field: 'locator', value: 'Другая глава' });
    editor.bookSource({ type: 'input', index: 0, field: 'locator', value: 'Глава 1' });

    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().needsGuard, false);
});

test('Снимок источников нельзя использовать для изменения состояния без команды', () => {
    const { editor } = setup();
    const snapshot = editor.getState();

    snapshot.sources[0].title = 'Подмена';
    snapshot.sources.push({ title: 'Лишний источник' });

    assert.equal(editor.getState().sources.length, 1);
    assert.equal(editor.getState().sources[0].title, 'Общий источник');
    assert.equal(editor.getState().dirty, false);
});

test('Некорректный источник не отправляется, после исправления запись доступна', async () => {
    const { editor, calls } = setup();

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: '' });
    await assert.rejects(editor.save(), TypeError);

    assert.equal(calls.length, 0);
    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().sources[0].title, '');

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: 'Исправленный источник' });
    await editor.save();

    assert.equal(calls.length, 1);
    assert.equal(editor.getState().sources[0].title, 'Исправленный источник');
    assert.equal(editor.getState().dirty, false);
});

test('Источники книги и текста сохраняются вместе, но остаются разными списками', async () => {
    const { editor, calls } = setup();

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: 'Источник книги' });
    editor.textSource('own', { type: 'input', index: 0, field: 'title', value: 'Источник раздела' });
    await editor.save();

    const content = calls[0].payload.content;

    assert.equal(content.sources[0].title, 'Источник книги');
    assert.equal(content.toc[0].content.sources[0].title, 'Источник раздела');
});

test('Загрузка серверного черновика заменяет и общие источники', async () => {
    const server = draft(4);
    server.content_json.sources = [{ title: 'Серверный источник' }];

    const { editor } = setup({
        async getWorkingEditor() {
            return {
                book: { id: BOOK },
                draft: server,
                latest_publication: null,
                has_unpublished_changes: true
            };
        }
    });

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: 'Локальная правка' });
    await editor.reload();

    assert.equal(editor.getState().revision, 4);
    assert.deepEqual(editor.getState().sources, server.content_json.sources);
    assert.equal(editor.getState().dirty, false);
});

test('Конфликт блокирует изменение источников и оставляет локальные правки', async () => {
    const { editor } = setup({
        async saveWorkingDraft() {
            throw Object.assign(new Error('Конфликт'), { status: 409 });
        }
    });

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: 'Локальный источник' });
    await editor.save();

    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.bookSource({ type: 'remove', index: 0 }), false);
    assert.equal(editor.getState().sources[0].title, 'Локальный источник');
});

test('Во время записи и после уничтожения редактора команды не применяются', async () => {
    let finish;
    let sent;
    const pending = new Promise((resolve) => { finish = resolve; });
    const { original, editor } = setup({
        saveWorkingDraft(bookId, payload) {
            sent = structuredClone(payload);
            return pending;
        }
    });

    editor.bookSource({ type: 'input', index: 0, field: 'title', value: 'Новый источник' });
    const saving = editor.save();

    assert.equal(editor.bookSource({ type: 'remove', index: 0 }), false);

    finish({ ...original, revision: 2, content_json: sent.content });
    await saving;
    editor.dispose();

    assert.equal(editor.bookSource({ type: 'remove', index: 0 }), false);
    assert.equal(editor.getState().sources[0].title, 'Новый источник');
});

test('Публикация сохраняет общие источники и подтверждает чистое состояние', async () => {
    const { editor } = setup();

    editor.bookSource({ type: 'input', index: 0, field: 'locator', value: 'Глава 7' });
    await editor.save();
    const result = await editor.publish();

    assert.ok(result);
    assert.equal(result.publication.content_json.sources[0].locator, 'Глава 7');
    assert.equal(editor.getState().sources[0].locator, 'Глава 7');
    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().canPublish, false);
});
