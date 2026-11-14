// tests/js/rules/rules-working-api.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { createBooksApi } from '../../../frontend/src/js/features/rules/books/books-api.js';
import { createRulesRequester, RulesRequestError } from '../../../frontend/src/js/features/rules/rules-http.js';

const BOOK = randomUUID();

function setup() {
    const calls = [];
    const response = { result: 'response' };
    const request = async (path, options) => {
        calls.push({ path, options });
        return response;
    };

    return { api: createBooksApi(request), calls, response };
}

test('Состояние редактора и рабочий черновик читаются по новым адресам', async () => {
    const { api, calls, response } = setup();
    const signal = new AbortController().signal;

    assert.equal(await api.getWorkingEditor(BOOK, { signal }), response);
    assert.equal(await api.getWorkingDraft(BOOK, { signal }), response);
    assert.deepEqual(calls, [
        { path: `/rules/books/${BOOK}/working-editor`, options: { signal } },
        { path: `/rules/books/${BOOK}/working-draft`, options: { signal } }
    ]);
});

test('Сохранение передаёт полный рабочий черновик и ожидаемую ревизию', async () => {
    const { api, calls, response } = setup();
    const signal = new AbortController().signal;
    const payload = {
        expected_revision: 3,
        content: {
            schema_version: 2,
            title: 'Книга',
            toc: [{
                kind: 'text',
                key: 'checks',
                parent_key: null,
                position: 0,
                title: null,
                content: { schema_version: 1, title: 'Проверки', body: '', sources: [] }
            }]
        }
    };

    assert.equal(await api.saveWorkingDraft(BOOK, payload, { signal }), response);
    assert.deepEqual(calls, [{
        path: `/rules/books/${BOOK}/working-draft`,
        options: { method: 'PUT', body: payload, signal }
    }]);
});

test('Выпуск передаёт ревизию без отдельной публикации внутренних статей', async () => {
    const { api, calls } = setup();
    const payload = { expected_revision: 4 };

    await api.publishWorkingDraft(BOOK, payload);

    assert.deepEqual(calls, [{
        path: `/rules/books/${BOOK}/working-draft/publish`,
        options: { method: 'POST', body: payload, signal: undefined }
    }]);
});

test('Некорректный идентификатор отклоняется до HTTP-запроса', () => {
    const { api, calls } = setup();

    for (const value of ['../book', '', null, 42]) {
        assert.throws(() => api.getWorkingEditor(value), TypeError);
        assert.throws(() => api.getWorkingDraft(value), TypeError);
        assert.throws(() => api.saveWorkingDraft(value, {}), TypeError);
        assert.throws(() => api.publishWorkingDraft(value, {}), TypeError);
    }

    assert.equal(calls.length, 0);
});

test('Конфликт передаётся вызывающему слою без повтора', async () => {
    let count = 0;
    const failure = new RulesRequestError('Конфликт ревизии', { status: 409 });
    const api = createBooksApi(async () => {
        count += 1;
        throw failure;
    });

    await assert.rejects(api.saveWorkingDraft(BOOK, {}), (error) => error === failure);
    assert.equal(count, 1);
});

test('Неопределённый результат выпуска не вызывает повторного запроса', async () => {
    const calls = [];
    const requester = createRulesRequester({
        async sessionFetch(path, options) {
            calls.push({ path, options });
            throw new TypeError('Соединение потеряно');
        }
    });
    const api = createBooksApi(requester);

    await assert.rejects(
        api.publishWorkingDraft(BOOK, { expected_revision: 4 }),
        (error) => error instanceof RulesRequestError && error.uncertain
    );

    assert.equal(calls.length, 1);
    assert.equal(calls[0].options.retryAfterRefresh, false);
});

test('Прежний API сохранения и выпуска не переключается скрытно', async () => {
    const { api, calls } = setup();

    await api.getDraft(BOOK);
    await api.saveDraft(BOOK, { expected_revision: 1, content: { schema_version: 1 } });
    await api.publish(BOOK, { expected_revision: 2 });

    assert.deepEqual(calls.map((call) => call.path), [
        `/rules/books/${BOOK}/draft`,
        `/rules/books/${BOOK}/draft`,
        `/rules/books/${BOOK}/publish`
    ]);
});
