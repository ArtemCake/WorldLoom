// tests/js/rules/rules-working-workspace.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { createAuthoringController } from '../../../frontend/src/js/features/rules/authoring/authoring-controller.js';
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
            sources: [{ title: 'Источник книги' }],
            toc: [{
                kind: 'text',
                key: 'own-text',
                parent_key: null,
                position: 0,
                title: null,
                content: {
                    schema_version: 1,
                    title: 'Проверки',
                    summary: 'Описание',
                    body: 'Исходный текст.',
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

function opened(source = draft()) {
    return {
        book: { id: BOOK },
        draft: structuredClone(source),
        latest_publication: null,
        has_unpublished_changes: true
    };
}

function setup() {
    const source = draft();
    let stored = structuredClone(source);
    const calls = [];
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
            return opened(stored);
        }
    };

    const editor = createBookDraftEditor({ draft: source, workingState: opened(source), api });
    return { source, editor, calls };
}

test('Контроллер открывает рабочую книгу с собственными текстами', async () => {
    const controller = createAuthoringController({
        api: {
            list: async () => ({ items: [], next_after: null }),
            getEditor: async () => opened()
        }
    });

    await controller.open(BOOK);
    const state = controller.getState();

    assert.equal(state.draftError, '');
    assert.equal(state.editor.draft.content_json.schema_version, 2);
    assert.equal(state.editor.draft.content_json.toc[0].kind, 'text');
    controller.dispose();
});

test('Контроллер принимает сохранённый рабочий черновик', async () => {
    const controller = createAuthoringController({
        api: {
            list: async () => ({ items: [], next_after: null }),
            getEditor: async () => opened()
        }
    });

    await controller.open(BOOK);
    const next = draft(2);
    next.content_json.toc[0].content.body = 'Сохранённая правка.';
    controller.acceptDraft(next);

    const state = controller.getState();

    assert.equal(state.editor.draft.revision, 2);
    assert.equal(state.editor.draft.content_json.toc[0].content.body, 'Сохранённая правка.');
    assert.equal(state.editor.has_unpublished_changes, true);
    controller.dispose();
});

test('Промежуточное пустое название остаётся локально и не отправляется на сервер', async () => {
    const { editor, calls } = setup();

    assert.equal(editor.changeText('own-text', 'title', ''), true);
    assert.equal(editor.getState().dirty, true);
    assert.equal(editor.getState().needsGuard, true);
    assert.equal(editor.getState().toc[0].content.title, '');

    await assert.rejects(editor.save(), TypeError);

    assert.equal(calls.length, 0);
    assert.equal(editor.getState().toc[0].content.title, '');
    assert.equal(editor.getState().blocked, false);
});

test('После исправления названия сохраняются все остальные данные', async () => {
    const { source, editor, calls } = setup();

    editor.changeText('own-text', 'title', '');
    editor.changeText('own-text', 'title', 'Обновлённые проверки');
    editor.changeText('own-text', 'body', 'Новая редакция.');
    await editor.save();

    const content = calls[0].payload.content;
    const own = content.toc[0].content;

    assert.equal(own.title, 'Обновлённые проверки');
    assert.equal(own.body, 'Новая редакция.');
    assert.equal(own.summary, 'Описание');
    assert.equal(own.audience, 'gm');
    assert.equal(own.rule_kind, 'homebrew');
    assert.deepEqual(own.sources, source.content_json.toc[0].content.sources);
    assert.deepEqual(content.sources, source.content_json.sources);
    assert.equal(source.content_json.toc[0].content.body, 'Исходный текст.');
    assert.equal(editor.getState().dirty, false);
});

test('Очистка редакции сохраняется как отсутствие редакции', async () => {
    const { editor, calls } = setup();

    editor.changeText('own-text', 'edition_key', '2014');
    editor.changeText('own-text', 'edition_key', '');
    editor.changeText('own-text', 'summary', 'Изменённое описание.');
    await editor.save();

    assert.equal(calls[0].payload.content.toc[0].content.edition_key, null);
});

test('Через ввод нельзя изменить источники, тип узла или произвольное поле', () => {
    const { editor } = setup();

    for (const field of ['sources', 'kind', 'article_version_id', 'unknown']) {
        assert.throws(() => editor.changeText('own-text', field, 'Подмена'), TypeError);
    }

    assert.equal(editor.getState().dirty, false);
});

test('Неизвестные аудитория и вид правила отклоняются без изменения текста', () => {
    const { editor } = setup();

    assert.throws(() => editor.changeText('own-text', 'audience', 'unknown'), TypeError);
    assert.throws(() => editor.changeText('own-text', 'rule_kind', 'unknown'), TypeError);
    assert.equal(editor.getState().dirty, false);
});

test('Несуществующий текст нельзя изменить', () => {
    const { editor } = setup();

    assert.throws(() => editor.changeText('missing', 'body', 'Подмена'), TypeError);
    assert.equal(editor.getState().dirty, false);
});

test('После уничтожения редактора ввод не применяется', () => {
    const { editor } = setup();

    editor.dispose();

    assert.equal(editor.changeText('own-text', 'body', 'Поздняя правка.'), false);
    assert.equal(editor.getState().toc[0].content.body, 'Исходный текст.');
});
