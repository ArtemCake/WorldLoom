// tests/js/rules/rules-draft-publication.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';
import { readBookPublication } from '../../../frontend/src/js/features/rules/draft/draft-publication-data.js';

const BOOK = '11111111-1111-4111-8111-111111111111';
const DRAFT = '22222222-2222-4222-8222-222222222222';
const SECTION = '33333333-3333-4333-8333-333333333333';
const PUBLICATION = '44444444-4444-4444-8444-444444444444';

function draft(revision = 1) {
    return {
        id: DRAFT,
        book_id: BOOK,
        revision,
        content_json: {
            schema_version: 1,
            title: 'Книга',
            summary: '',
            introduction: '',
            language: 'ru',
            edition_key: null,
            category: 'rules',
            audience: 'gm',
            sources: [],
            toc: [{
                kind: 'article',
                key: 'checks',
                parent_key: null,
                position: 0,
                title: 'Проверки',
                article_version_id: SECTION
            }]
        }
    };
}

function publication(source = draft()) {
    return {
        publication: {
            id: PUBLICATION,
            book_id: BOOK,
            version_number: 1,
            source_draft_revision: source.revision,
            content_json: structuredClone(source.content_json)
        },
        draft_revision: source.revision + 1
    };
}

function failure(status, uncertain = false) {
    return Object.assign(new Error('Ошибка запроса'), { status, uncertain });
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function setup(overrides = {}, source = draft()) {
    const calls = [];
    const api = {
        getDraft: async () => draft(2),
        saveDraft: async (_bookId, payload) => {
            return { ...draft(payload.expected_revision + 1), content_json: structuredClone(payload.content) };
        },
        publish: async (bookId, payload) => {
            calls.push({ bookId, payload });
            return publication(source);
        },
        ...overrides
    };

    return { editor: createBookDraftEditor({ draft: source, api }), calls };
}

test('Выпуск отправляет ревизию и принимает обновлённый серверный черновик', async () => {
    const { editor, calls } = setup();

    assert.equal(editor.getState().canPublish, true);
    const result = await editor.publish();

    assert.deepEqual(calls, [{ bookId: BOOK, payload: { expected_revision: 1 } }]);
    assert.equal(result.publication.id, PUBLICATION);
    assert.equal(result.draft.revision, 2);
    assert.equal(editor.getState().revision, 2);
    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().lastPublication.version_number, 1);
});

test('Несохранённые изменения не публикуются и не сохраняются автоматически', async () => {
    const { editor, calls } = setup({
        saveDraft: async () => assert.fail('Автосохранения быть не должно')
    });

    editor.change('title', 'Локальная правка');

    assert.equal(editor.getState().canPublish, false);
    assert.equal(await editor.publish(), null);
    assert.equal(calls.length, 0);
    assert.equal(editor.getState().values.title, 'Локальная правка');
});

test('Книга без разделов не отправляется на публикацию', async () => {
    const source = draft();
    source.content_json.toc = [];
    const { editor, calls } = setup({}, source);

    assert.equal(editor.getState().canPublish, false);
    assert.equal(await editor.publish(), null);
    assert.equal(calls.length, 0);
});

test('Во время публикации запрещены повторный выпуск, запись и изменение формы', async () => {
    const pending = deferred();
    let count = 0;
    const { editor } = setup({
        publish: async () => {
            count += 1;
            return pending.promise;
        }
    });

    const publishing = editor.publish();
    editor.change('title', 'Не применять');

    assert.equal(editor.getState().busy, 'publish');
    assert.equal(editor.getState().needsGuard, true);
    assert.equal(editor.getState().values.title, 'Книга');
    assert.equal(await editor.publish(), null);
    assert.equal(await editor.save(), null);
    assert.equal(await editor.reload(), null);
    assert.equal(count, 1);

    pending.resolve(publication());
    await publishing;

    assert.equal(editor.getState().busy, '');
});

test('Подтверждённый выпуск не повторяется для той же ревизии', async () => {
    const { editor, calls } = setup();

    await editor.publish();

    assert.equal(editor.getState().canPublish, false);
    assert.equal(await editor.publish(), null);
    assert.equal(calls.length, 1);

    await editor.reload();

    assert.equal(editor.getState().canPublish, false);
});

test('Сохранение последующих изменений снова разрешает выпуск', async () => {
    const { editor } = setup();

    await editor.publish();
    editor.change('title', 'Следующая редакция');
    await editor.save();

    assert.equal(editor.getState().revision, 3);
    assert.equal(editor.getState().canPublish, true);
});

test('Потерянный ответ блокирует повтор, но не объявляется подтверждённым отказом', async () => {
    let count = 0;
    const { editor } = setup({
        publish: async () => {
            count += 1;
            throw failure(0, true);
        }
    });

    assert.equal(await editor.publish(), null);
    assert.equal(await editor.publish(), null);
    assert.equal(count, 1);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().lastPublication, null);
    assert.match(editor.getState().error, /могла быть создана/u);
});

test('Подмена содержания ответа не подтверждает успешный выпуск', async () => {
    const response = publication();
    response.publication.content_json.title = 'Другая книга';
    const { editor } = setup({ publish: async () => response });

    assert.equal(await editor.publish(), null);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().lastPublication, null);
    assert.equal(editor.getState().values.title, 'Книга');
});

test('Ошибка чтения после подтверждённого выпуска не отменяет его результат', async () => {
    const { editor, calls } = setup({
        getDraft: async () => { throw failure(503); }
    });

    const result = await editor.publish();

    assert.equal(result.publication.id, PUBLICATION);
    assert.equal(result.draft, null);
    assert.equal(editor.getState().lastPublication.id, PUBLICATION);
    assert.equal(editor.getState().blocked, true);
    assert.match(editor.getState().message, /Создана публикация/u);
    assert.match(editor.getState().error, /Публикация создана/u);
    assert.equal(await editor.publish(), null);
    assert.equal(calls.length, 1);
});

test('Более новый черновик после выпуска не затирает открытую форму', async () => {
    const newer = draft(3);
    newer.content_json.title = 'Правка из другой вкладки';
    const { editor } = setup({ getDraft: async () => newer });

    const result = await editor.publish();

    assert.equal(result.publication.id, PUBLICATION);
    assert.equal(result.draft, null);
    assert.equal(editor.getState().values.title, 'Книга');
    assert.equal(editor.getState().blocked, true);

    await editor.reload();

    assert.equal(editor.getState().values.title, 'Правка из другой вкладки');
    assert.equal(editor.getState().revision, 3);
    assert.equal(editor.getState().blocked, false);
});

test('Конфликт сервера блокирует публикацию до загрузки черновика', async () => {
    const { editor } = setup({ publish: async () => { throw failure(409); } });

    assert.equal(await editor.publish(), null);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().lastPublication, null);

    await editor.reload();

    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().revision, 2);
});

test('Ответ проверяется по книге, исходной и следующей ревизиям', () => {
    const wrongBook = publication();
    wrongBook.publication.book_id = SECTION;

    const wrongSource = publication();
    wrongSource.publication.source_draft_revision = 2;

    const wrongRevision = publication();
    wrongRevision.draft_revision = 3;

    for (const response of [wrongBook, wrongSource, wrongRevision]) {
        assert.throws(() => readBookPublication(response, BOOK, 1), TypeError);
    }
});

test('После уничтожения редактора ответ не публикует обновления интерфейса', async () => {
    const pending = deferred();
    const states = [];
    const api = {
        saveDraft: async () => assert.fail('Сохранение не ожидается'),
        getDraft: async () => assert.fail('Закрытый редактор не должен начинать чтение'),
        publish: async () => pending.promise
    };
    const editor = createBookDraftEditor({ draft: draft(), api, onChange: (state) => states.push(state) });

    const publishing = editor.publish();
    editor.dispose();
    const count = states.length;

    pending.resolve(publication());
    await publishing;

    assert.equal(states.length, count);
});
