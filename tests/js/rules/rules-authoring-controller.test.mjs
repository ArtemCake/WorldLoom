// tests/js/rules/rules-authoring-controller.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createAuthoringController } from '../../../frontend/src/js/features/rules/authoring/authoring-controller.js';

const FIRST = '11111111-1111-4111-8111-111111111111';
const SECOND = '22222222-2222-4222-8222-222222222222';

function item(id = FIRST) {
    return {
        id,
        system_id: FIRST,
        title: 'Книга правил',
        summary: '',
        language: 'ru',
        edition_key: null,
        visibility: 'private',
        is_active: true,
        draft_revision: 1,
        version_id: null,
        version_number: null,
        has_unpublished_changes: true
    };
}

function page(items = [], nextAfter = null) {
    return { items, next_after: nextAfter };
}

function editor(id = FIRST) {
    return {
        book: { id },
        draft: {
            book_id: id,
            revision: 1,
            content_json: {
                schema_version: 1,
                title: 'Черновик книги',
                summary: '',
                introduction: '',
                language: 'ru',
                edition_key: null,
                sources: [],
                toc: []
            }
        }
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function create(api) {
    return createAuthoringController({ api: { getEditor: async (id) => editor(id), ...api } });
}

test('Система и поиск сохраняются при продолжении списка', async () => {
    const calls = [];
    const responses = [page([item()], FIRST), page([item(SECOND)])];
    const controller = create({
        list: async (query) => {
            calls.push(query);
            return responses.shift();
        }
    });

    await controller.reload({ system_id: FIRST, q: 'Правила' });
    await controller.next();

    assert.equal(calls[1].system_id, FIRST);
    assert.equal(calls[1].q, 'Правила');
    assert.equal(calls[1].after, FIRST);
    assert.deepEqual(controller.getState().items.map((book) => book.id), [FIRST, SECOND]);
});

test('Смена фильтров не принимает запоздавшую страницу', async () => {
    const old = deferred();
    let signal;
    const controller = create({
        list: async (query, options) => {
            if (query.system_id === FIRST) {
                signal = options.signal;
                return old.promise;
            }
            return page([item(SECOND)]);
        }
    });

    const pending = controller.reload({ system_id: FIRST });
    await controller.reload({ system_id: SECOND });
    old.resolve(page([item()]));
    await pending;

    assert.equal(signal.aborted, true);
    assert.equal(controller.getState().items[0].id, SECOND);
});

test('Ошибка продолжения сохраняет карточки и курсор для повтора', async () => {
    let attempt = 0;
    const controller = create({
        list: async () => {
            attempt += 1;
            if (attempt === 1) return page([item()], FIRST);
            if (attempt === 2) throw new Error('Временная ошибка');
            return page([item(SECOND)]);
        }
    });

    await controller.reload();
    await controller.next();
    assert.equal(controller.getState().items.length, 1);
    assert.equal(controller.getState().nextAfter, FIRST);

    await controller.next();
    assert.equal(controller.getState().items.length, 2);
    assert.equal(controller.getState().error, '');
});

test('Возврат из черновика не загружает каталог заново', async () => {
    let calls = 0;
    const controller = create({
        list: async () => {
            calls += 1;
            return page([item()], FIRST);
        }
    });

    await controller.reload({ q: 'Книга' });
    await controller.open(FIRST);
    controller.close();

    const state = controller.getState();
    assert.equal(calls, 1);
    assert.equal(state.filters.q, 'Книга');
    assert.equal(state.items.length, 1);
    assert.equal(state.nextAfter, FIRST);
    assert.equal(state.opened, false);
});

test('Закрытый черновик не появляется после завершения запроса', async () => {
    const pending = deferred();
    let signal;
    const controller = create({
        list: async () => page(),
        getEditor: async (_id, options) => {
            signal = options.signal;
            return pending.promise;
        }
    });

    const opening = controller.open(FIRST);
    controller.close();
    pending.resolve(editor());
    await opening;

    assert.equal(signal.aborted, true);
    assert.equal(controller.getState().opened, false);
    assert.equal(controller.getState().editor, null);
});

test('Ответ другой книги отклоняется', async () => {
    const controller = create({
        list: async () => page(),
        getEditor: async () => editor(SECOND)
    });

    await controller.open(FIRST);

    assert.equal(controller.getState().editor, null);
    assert.ok(controller.getState().draftError);
});

test('Циклическое оглавление не передаётся представлению', async () => {
    const data = editor();
    data.draft.content_json.toc = [
        { key: 'loop', kind: 'chapter', title: 'Глава', parent_key: 'loop', position: 0 }
    ];
    const controller = create({ list: async () => page(), getEditor: async () => data });

    await controller.open(FIRST);

    assert.equal(controller.getState().editor, null);
    assert.ok(controller.getState().draftError);
});

test('Повторяющийся курсор не запускает бесконечное продолжение', async () => {
    const controller = create({ list: async () => page([item()], FIRST) });

    await controller.reload();
    await controller.next();

    assert.ok(controller.getState().error);
    assert.equal(controller.getState().items.length, 1);
});

test('Внешнее изменение снимка не меняет состояние контроллера', async () => {
    const controller = create({ list: async () => page([item()]) });
    await controller.reload();
    await controller.open(FIRST);

    const snapshot = controller.getState();
    snapshot.items[0].title = 'Подмена';
    snapshot.editor.draft.content_json.title = 'Подмена';
    snapshot.filters.q = 'Подмена';

    const current = controller.getState();
    assert.equal(current.items[0].title, 'Книга правил');
    assert.equal(current.editor.draft.content_json.title, 'Черновик книги');
    assert.equal(current.filters.q, '');
});

test('После уничтожения ответ запроса не изменяет состояние', async () => {
    const pending = deferred();
    const controller = create({ list: async () => pending.promise });

    const loading = controller.reload();
    controller.dispose();
    pending.resolve(page([item()]));
    await loading;

    assert.equal(controller.getState().items.length, 0);
});
