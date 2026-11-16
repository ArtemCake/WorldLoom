// tests/js/rules/rules-working-editor-state.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';
import { assertWorkingPublication, readWorkingEditor } from '../../../frontend/src/js/features/rules/draft/draft-working-data.js';

const BOOK = randomUUID();
const DRAFT = randomUUID();
const PUBLICATION = randomUUID();
const SNAPSHOT = randomUUID();
const EXTERNAL = randomUUID();

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
            sources: [{ title: 'Источник книги' }],
            toc: [{
                kind: 'text',
                key: 'checks',
                parent_key: null,
                position: 0,
                title: null,
                content: {
                    schema_version: 1,
                    title: 'Проверки',
                    summary: 'Описание',
                    body: 'Первая редакция.',
                    language: 'ru',
                    edition_key: null,
                    audience: 'gm',
                    rule_kind: 'homebrew',
                    sources: [{ title: 'Источник текста', locator: 'Раздел 2' }]
                }
            }]
        }
    };
}

function release(source) {
    const content = structuredClone(source.content_json);
    content.schema_version = 1;
    content.toc = content.toc.map((node) => {
        if (node.kind !== 'text') return node;

        const result = { ...node, kind: 'article', article_version_id: SNAPSHOT };
        delete result.content;
        return result;
    });

    return {
        publication: {
            id: PUBLICATION,
            book_id: BOOK,
            version_number: 1,
            source_draft_revision: source.revision,
            content_json: content
        },
        draft_revision: source.revision + 1
    };
}

function opened(source, publication = null, changed = true) {
    return {
        book: { id: BOOK },
        draft: structuredClone(source),
        latest_publication: structuredClone(publication),
        has_unpublished_changes: changed
    };
}

function setup(source = draft(), initial = opened(source), overrides = {}) {
    let stored = structuredClone(source);
    let latest = structuredClone(initial.latest_publication);
    let changed = initial.has_unpublished_changes;
    const calls = [];

    const api = {
        async saveWorkingDraft(bookId, payload) {
            calls.push({ operation: 'save', bookId, payload: structuredClone(payload) });
            stored = {
                ...stored,
                revision: payload.expected_revision + 1,
                content_json: structuredClone(payload.content)
            };
            changed = true;
            return structuredClone(stored);
        },

        async publishWorkingDraft(bookId, payload) {
            calls.push({ operation: 'publish', bookId, payload: structuredClone(payload) });
            const result = release(stored);
            latest = structuredClone(result.publication);
            stored.revision = result.draft_revision;
            changed = false;
            return result;
        },

        async getWorkingEditor(bookId) {
            calls.push({ operation: 'read', bookId });
            return opened(stored, latest, changed);
        },

        ...overrides
    };

    const editor = createBookDraftEditor({ draft: source, api, workingState: initial });
    return { editor, calls };
}

function replaceBody(editor, body) {
    const content = editor.getState().toc[0].content;
    return editor.text({ type: 'update', key: 'checks', content: { ...content, body } });
}

test('Книгу только с собственным текстом можно подготовить к выпуску', () => {
    const { editor } = setup();

    assert.equal(editor.getState().canPublish, true);
    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().lastPublication, null);
});

test('Рабочий формат требует согласованного начального состояния', () => {
    const source = draft();
    const api = { saveWorkingDraft() {}, getWorkingEditor() {} };

    assert.throws(() => createBookDraftEditor({ draft: source, api }), TypeError);

    const other = draft(2);
    assert.throws(() => createBookDraftEditor({ draft: source, api, workingState: opened(other) }), TypeError);
});

test('Изменение текста сохраняется вместе с остальными полями и источниками', async () => {
    const source = draft();
    const before = structuredClone(source);
    const { editor, calls } = setup(source);

    assert.equal(replaceBody(editor, 'Новая редакция.'), true);
    editor.change('title', 'Обновлённая книга');
    assert.equal(editor.getState().canPublish, false);

    const saved = await editor.save();
    const sent = calls[0].payload.content;

    assert.equal(saved.revision, 2);
    assert.equal(sent.schema_version, 2);
    assert.equal(sent.title, 'Обновлённая книга');
    assert.equal(sent.toc[0].content.body, 'Новая редакция.');
    assert.equal(sent.toc[0].content.audience, 'gm');
    assert.equal(sent.toc[0].content.rule_kind, 'homebrew');
    assert.deepEqual(sent.sources, before.content_json.sources);
    assert.deepEqual(sent.toc[0].content.sources, before.content_json.toc[0].content.sources);
    assert.deepEqual(source, before);
    assert.equal(editor.getState().dirty, false);
});

test('Пустой рабочий текст можно сохранить', async () => {
    const { editor } = setup();

    replaceBody(editor, '');
    const saved = await editor.save();

    assert.equal(saved.content_json.toc[0].content.body, '');
});

test('Выпуск проверяет материализацию и повторно читает согласованное состояние', async () => {
    const { editor, calls } = setup();
    const result = await editor.publish();

    assert.equal(result.publication.id, PUBLICATION);
    assert.equal(result.draft.revision, 2);
    assert.equal(result.draft.content_json.toc[0].kind, 'text');
    assert.equal(result.publication.content_json.toc[0].kind, 'article');
    assert.deepEqual(calls.map((call) => call.operation), ['publish', 'read']);
    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().canPublish, false);
    assert.equal(await editor.publish(), null);
    assert.equal(calls.length, 2);
});

test('Уже опубликованное содержание не предлагает повторный выпуск при открытии', () => {
    const source = draft();
    const result = release(source);
    source.revision = result.draft_revision;
    const state = opened(source, result.publication, false);
    const { editor } = setup(source, state);

    assert.equal(editor.getState().lastPublication.id, PUBLICATION);
    assert.equal(editor.getState().canPublish, false);
});

test('Возврат к известному опубликованному содержанию снимает возможность повторного выпуска', async () => {
    const { editor } = setup();
    await editor.publish();

    replaceBody(editor, 'Изменение.');
    await editor.save();
    assert.equal(editor.getState().canPublish, true);

    replaceBody(editor, 'Первая редакция.');
    await editor.save();
    assert.equal(editor.getState().canPublish, false);
});

test('Конфликт сохранения сохраняет локальный текст и блокирует последующие команды', async () => {
    const { editor } = setup(undefined, undefined, {
        async saveWorkingDraft() {
            throw Object.assign(new Error('Конфликт'), { status: 409 });
        }
    });

    replaceBody(editor, 'Локальная правка.');
    assert.equal(await editor.save(), null);
    assert.equal(editor.getState().blocked, true);
    assert.equal(replaceBody(editor, 'Не применять.'), false);
    assert.equal(editor.getState().toc[0].content.body, 'Локальная правка.');
});

test('Неопределённый выпуск не повторяется автоматически', async () => {
    let count = 0;
    const { editor } = setup(undefined, undefined, {
        async publishWorkingDraft() {
            count += 1;
            throw Object.assign(new Error('Соединение потеряно'), { uncertain: true });
        }
    });

    assert.equal(await editor.publish(), null);
    assert.equal(editor.getState().blocked, true);
    assert.equal(await editor.publish(), null);
    assert.equal(count, 1);
});

test('Подтверждённый выпуск не теряется при ошибке последующего чтения', async () => {
    const { editor } = setup(undefined, undefined, {
        async getWorkingEditor() {
            throw new Error('Чтение недоступно');
        }
    });

    const result = await editor.publish();

    assert.equal(result.publication.id, PUBLICATION);
    assert.equal(result.draft, null);
    assert.equal(editor.getState().lastPublication.id, PUBLICATION);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().revision, 1);
    assert.equal(editor.getState().toc[0].kind, 'text');
});

test('Несовпадение с серверной публикацией блокирует запись после подтверждённого выпуска', async () => {
    const source = draft();
    const result = release(source);
    const next = { ...structuredClone(source), revision: 2 };

    const { editor } = setup(source, opened(source), {
        async getWorkingEditor() {
            return opened(next, result.publication, true);
        }
    });

    const published = await editor.publish();

    assert.equal(published.publication.id, PUBLICATION);
    assert.equal(published.draft, null);
    assert.equal(editor.getState().blocked, true);
});

test('Другая последняя публикация не принимается за результат текущего выпуска', async () => {
    const source = draft();
    const result = release(source);
    const next = { ...structuredClone(source), revision: 2 };
    const other = { ...result.publication, id: randomUUID() };

    const { editor } = setup(source, opened(source), {
        async getWorkingEditor() {
            return opened(next, other, false);
        }
    });

    const published = await editor.publish();

    assert.equal(published.draft, null);
    assert.equal(editor.getState().blocked, true);
});

test('Явная загрузка снимает блокировку и обновляет сведения о публикации', async () => {
    const source = draft();
    const result = release(source);
    const next = { ...structuredClone(source), revision: 2 };

    const { editor } = setup(source, opened(source), {
        async saveWorkingDraft() {
            throw Object.assign(new Error('Конфликт'), { status: 409 });
        },

        async getWorkingEditor() {
            return opened(next, result.publication, false);
        }
    });

    replaceBody(editor, 'Локальная правка.');
    await editor.save();
    assert.equal(editor.getState().blocked, true);

    const loaded = await editor.reload();

    assert.equal(loaded.revision, 2);
    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().lastPublication.id, PUBLICATION);
    assert.equal(editor.getState().canPublish, false);
});

test('Материализация не допускает изменения введения или подмены собственного текста внешним', () => {
    const source = draft();
    const content = source.content_json;
    const result = release(source);

    assert.doesNotThrow(() => assertWorkingPublication(content, result.publication.content_json));

    const changed = structuredClone(result.publication.content_json);
    changed.introduction = 'Постороннее изменение.';
    assert.throws(() => assertWorkingPublication(content, changed), TypeError);

    content.toc.push({
        kind: 'article',
        key: 'external',
        parent_key: null,
        position: 1,
        title: null,
        article_version_id: EXTERNAL
    });

    const replaced = release(source).publication.content_json;
    replaced.toc[0].article_version_id = EXTERNAL;
    assert.throws(() => assertWorkingPublication(content, replaced), TypeError);
});

test('Состояние без публикации не может сообщать об опубликованном содержании', () => {
    assert.throws(() => readWorkingEditor(opened(draft(), null, false), BOOK), TypeError);
});

test('Поздний ответ сохранения не изменяет уничтоженный редактор', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const source = draft();

    const { editor } = setup(source, opened(source), {
        saveWorkingDraft: () => pending
    });

    replaceBody(editor, 'Локальная правка.');
    const saving = editor.save();
    editor.dispose();

    const saved = structuredClone(source);
    saved.revision = 2;
    saved.content_json.toc[0].content.body = 'Локальная правка.';
    finish(saved);

    assert.equal(await saving, null);
    assert.equal(editor.getState().revision, 1);
});
