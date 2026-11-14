// tests/js/rules/rules-draft-editor-state.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';

const BOOK = '11111111-1111-4111-8111-111111111111';
const DRAFT = '22222222-2222-4222-8222-222222222222';
const VERSION = '33333333-3333-4333-8333-333333333333';

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
            sources: [{ title: 'Источник', locator: 'Глава 2' }],
            toc: [
                { kind: 'chapter', key: 'main', parent_key: null, position: 0, title: 'Основы' },
                { kind: 'article', key: 'check', parent_key: 'main', position: 0, title: null, article_version_id: VERSION }
            ]
        }
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function failure(status, uncertain = false) {
    return Object.assign(new Error('Ошибка запроса'), { status, uncertain });
}

function setup(overrides = {}, source = draft()) {
    const calls = [];
    const api = {
        getDraft: async () => draft(2),
        saveDraft: async (bookId, payload) => {
            calls.push({ bookId, payload: structuredClone(payload) });
            return { ...draft(payload.expected_revision + 1), content_json: structuredClone(payload.content) };
        },
        ...overrides
    };

    return { editor: createBookDraftEditor({ draft: source, api }), calls };
}

test('Редактор сохраняет ревизию и все нередактируемые части содержания', async () => {
    const source = draft();
    const { editor, calls } = setup({}, source);

    editor.change('title', 'Новое название');
    editor.change('introduction', 'Новое введение');
    const saved = await editor.save();

    assert.equal(calls[0].bookId, BOOK);
    assert.equal(calls[0].payload.expected_revision, 1);
    assert.equal(calls[0].payload.content.title, 'Новое название');
    assert.deepEqual(calls[0].payload.content.toc, source.content_json.toc);
    assert.deepEqual(calls[0].payload.content.sources, source.content_json.sources);
    assert.equal(calls[0].payload.content.audience, 'gm');
    assert.equal(calls[0].payload.content.category, 'rules');
    assert.equal(saved.revision, 2);
    assert.equal(editor.getState().dirty, false);
    assert.equal(source.content_json.title, 'Книга');
});

test('Без изменений запись не отправляется', async () => {
    const { editor, calls } = setup();

    assert.equal(await editor.save(), null);
    assert.equal(calls.length, 0);
});

test('Возврат исходного значения снимает признак изменений', () => {
    const { editor } = setup();

    editor.change('title', 'Другое');
    assert.equal(editor.getState().dirty, true);

    editor.change('title', 'Книга');
    assert.equal(editor.getState().needsGuard, false);
});

test('Пустой код редакции отправляется как null', async () => {
    const source = draft();
    source.content_json.edition_key = '2014';
    const { editor, calls } = setup({}, source);

    editor.change('edition_key', '');
    await editor.save();

    assert.equal(calls[0].payload.content.edition_key, null);
});

test('Недопустимые поля не редактируются', () => {
    const { editor } = setup();

    assert.throws(() => editor.change('toc', 'подмена'), TypeError);
    assert.throws(() => editor.change('audience', 'players'), TypeError);
});

test('Пустое название отклоняется до обращения к серверу', async () => {
    const { editor, calls } = setup();
    editor.change('title', '   ');

    await assert.rejects(editor.save(), /название/u);
    assert.equal(calls.length, 0);
    assert.equal(editor.getState().values.title, '   ');
});

test('Повторная запись и ввод во время запроса блокируются', async () => {
    const pending = deferred();
    let calls = 0;
    const { editor } = setup({
        saveDraft: async () => {
            calls += 1;
            return pending.promise;
        }
    });

    editor.change('title', 'Изменено');
    const saving = editor.save();
    editor.change('title', 'Не должно примениться');

    assert.equal(await editor.save(), null);
    assert.equal(calls, 1);
    assert.equal(editor.getState().values.title, 'Изменено');

    const saved = draft(2);
    saved.content_json.title = 'Изменено';
    pending.resolve(saved);
    await saving;

    assert.equal(editor.getState().dirty, false);
});

test('Конфликт сохраняет локальный текст и блокирует повторную запись', async () => {
    let calls = 0;
    const { editor } = setup({
        saveDraft: async () => {
            calls += 1;
            throw failure(409);
        }
    });

    editor.change('title', 'Локальное название');
    await editor.save();
    await editor.save();

    assert.equal(calls, 1);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().values.title, 'Локальное название');
    assert.equal(editor.getState().dirty, true);
});

test('Потерянный ответ не объявляется подтверждённым отказом записи', async () => {
    const { editor } = setup({ saveDraft: async () => { throw failure(0, true); } });

    editor.change('introduction', 'Локальный текст');
    await editor.save();

    const state = editor.getState();
    assert.equal(state.blocked, true);
    assert.match(state.error, /могла выполниться/u);
    assert.equal(state.values.introduction, 'Локальный текст');
    assert.equal(state.message, '');
});

test('Ответ с изменённым оглавлением не подтверждает корректное сохранение', async () => {
    const { editor } = setup({
        saveDraft: async (_bookId, payload) => {
            const saved = draft(2);
            saved.content_json = { ...payload.content, toc: [] };
            return saved;
        }
    });

    editor.change('title', 'Новое');
    assert.equal(await editor.save(), null);
    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().dirty, true);
});

test('Ответ другой книги не принимается', async () => {
    const { editor } = setup({
        saveDraft: async () => ({ ...draft(2), book_id: VERSION })
    });

    editor.change('title', 'Новое');
    await editor.save();

    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().revision, 1);
});

test('Ошибка валидации сервера разрешает исправить и повторить запись', async () => {
    const { editor } = setup({ saveDraft: async () => { throw failure(422); } });

    editor.change('title', 'Новое');
    await editor.save();

    assert.equal(editor.getState().blocked, false);
    editor.change('title', 'Исправлено');
    assert.equal(editor.getState().canSave, true);
});

test('Неудачное чтение после конфликта сохраняет локальную форму', async () => {
    const { editor } = setup({
        saveDraft: async () => { throw failure(409); },
        getDraft: async () => { throw failure(503); }
    });

    editor.change('title', 'Локальный текст');
    await editor.save();
    await editor.reload();

    assert.equal(editor.getState().values.title, 'Локальный текст');
    assert.equal(editor.getState().blocked, true);
});

test('Явная загрузка серверного черновика заменяет форму и снимает блокировку', async () => {
    const server = draft(5);
    server.content_json.title = 'Серверное название';
    const { editor } = setup({
        saveDraft: async () => { throw failure(409); },
        getDraft: async () => server
    });

    editor.change('title', 'Локальный текст');
    await editor.save();
    await editor.reload();

    assert.equal(editor.getState().values.title, 'Серверное название');
    assert.equal(editor.getState().revision, 5);
    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().dirty, false);
});

test('Внешнее изменение снимка не изменяет форму', () => {
    const { editor } = setup();
    const snapshot = editor.getState();
    snapshot.values.title = 'Подмена';

    assert.equal(editor.getState().values.title, 'Книга');
});

test('Порядок ключей в серверном JSON не создаёт ложную ошибку', async () => {
    const { editor } = setup({
        saveDraft: async (_bookId, payload) => {
            const content = Object.fromEntries(Object.entries(payload.content).reverse());
            return { ...draft(2), content_json: content };
        }
    });

    editor.change('title', 'Новое');
    await editor.save();

    assert.equal(editor.getState().blocked, false);
    assert.equal(editor.getState().dirty, false);
});

test('Изменение только главы включает сохранение и предупреждение о выходе', async () => {
    const { editor, calls } = setup();

    editor.chapter({ type: 'rename', key: 'main', title: 'Новая глава' });

    assert.equal(editor.getState().dirty, true);
    assert.equal(editor.getState().needsGuard, true);
    assert.equal(editor.getState().canSave, true);

    await editor.save();

    assert.equal(calls[0].payload.content.toc[0].title, 'Новая глава');
    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().revision, 2);
});

test('Сведения и структура сохраняются одним запросом без потери источников', async () => {
    const source = draft();
    const { editor, calls } = setup({}, source);

    editor.change('title', 'Новое название книги');
    editor.chapter({ type: 'add', key: 'extra', parent_key: null, title: 'Дополнение' });
    await editor.save();

    const content = calls[0].payload.content;

    assert.equal(calls.length, 1);
    assert.equal(content.title, 'Новое название книги');
    assert.equal(content.toc.length, 3);
    assert.deepEqual(content.toc[1], source.content_json.toc[1]);
    assert.deepEqual(content.sources, source.content_json.sources);
    assert.equal(content.category, source.content_json.category);
    assert.equal(content.audience, source.content_json.audience);
});

test('Возврат исходного названия главы снимает признак изменений', () => {
    const { editor } = setup();

    editor.chapter({ type: 'rename', key: 'main', title: 'Другое' });
    editor.chapter({ type: 'rename', key: 'main', title: 'Основы' });

    assert.equal(editor.getState().dirty, false);
    assert.equal(editor.getState().needsGuard, false);
});

test('Конфликт записи сохраняет локальную структуру и блокирует дальнейшие команды', async () => {
    const { editor } = setup({ saveDraft: async () => { throw failure(409); } });

    editor.chapter({ type: 'rename', key: 'main', title: 'Локальная глава' });
    await editor.save();
    editor.chapter({ type: 'rename', key: 'main', title: 'Не должно примениться' });

    assert.equal(editor.getState().blocked, true);
    assert.equal(editor.getState().toc[0].title, 'Локальная глава');
    assert.equal(editor.getState().dirty, true);
});

test('Загрузка серверного состояния заменяет также локальное оглавление', async () => {
    const server = draft(5);
    server.content_json.toc[0].title = 'Серверная глава';
    const { editor } = setup({ getDraft: async () => server });

    editor.chapter({ type: 'rename', key: 'main', title: 'Локальная глава' });
    await editor.reload();

    assert.equal(editor.getState().toc[0].title, 'Серверная глава');
    assert.equal(editor.getState().revision, 5);
    assert.equal(editor.getState().dirty, false);
});

test('Изменение полученного снимка структуры не меняет редактор', () => {
    const { editor } = setup();
    const state = editor.getState();
    state.toc[0].title = 'Подмена';

    assert.equal(editor.getState().toc[0].title, 'Основы');
});

test('Новый раздел сохраняется вместе со сведениями и прежними источниками', async () => {
    const source = draft();
    const { editor, calls } = setup({}, source);
    const articleId = '44444444-4444-4444-8444-444444444444';
    const versionId = '55555555-5555-4555-8555-555555555555';

    editor.change('title', 'Обновлённая книга');
    editor.section({
        type: 'attach',
        key: 'new-section',
        parent_key: 'main',
        publication: {
            id: versionId,
            article_id: articleId,
            version_number: 1,
            content_json: { schema_version: 1, title: 'Новый раздел', body: 'Текст', sources: [] }
        }
    });

    assert.equal(editor.getState().dirty, true);
    await editor.save();

    const content = calls[0].payload.content;

    assert.equal(calls.length, 1);
    assert.equal(content.title, 'Обновлённая книга');
    assert.equal(content.toc.at(-1).article_version_id, versionId);
    assert.deepEqual(content.sources, source.content_json.sources);
    assert.deepEqual(content.toc[1], source.content_json.toc[1]);
    assert.equal(editor.getState().dirty, false);
});

test('Удаление раздела отмечается как несохранённое изменение', () => {
    const { editor } = setup();

    assert.equal(editor.section({ type: 'remove', key: 'check' }), true);
    assert.equal(editor.getState().toc.some((node) => node.key === 'check'), false);
    assert.equal(editor.getState().needsGuard, true);
});

test('После конфликта команды разделов не меняют локальное оглавление', async () => {
    const { editor } = setup({ saveDraft: async () => { throw failure(409); } });

    editor.section({ type: 'remove', key: 'check' });
    await editor.save();

    const before = editor.getState().toc;
    assert.equal(editor.section({ type: 'remove', key: 'missing' }), false);
    assert.deepEqual(editor.getState().toc, before);
    assert.equal(editor.getState().blocked, true);
});