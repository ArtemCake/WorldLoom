// tests/js/rules/rules-book-reader.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createBookReader, parseBookReading } from '../../../frontend/src/js/features/rules/book-reader.js';

const BOOK = '11111111-1111-4111-8111-111111111111';
const VERSION = '22222222-2222-4222-8222-222222222222';
const TEXT_VERSION = '33333333-3333-4333-8333-333333333333';

function reading(title = 'Основные правила') {
    return {
        publication: {
            id: VERSION,
            book_id: BOOK,
            version_number: 1,
            content_json: { schema_version: 1, title, introduction: 'Введение', sources: [] }
        },
        articles: [{
            id: TEXT_VERSION,
            content_json: { schema_version: 1, title: 'Проверки', body: 'Текст правила', sources: [] }
        }],
        toc: [
            {
                kind: 'chapter',
                key: 'basics',
                parent_key: null,
                position: 0,
                depth: 0,
                title: 'Основы',
                article_version_id: null
            },
            {
                kind: 'article',
                key: 'checks',
                parent_key: 'basics',
                position: 0,
                depth: 1,
                title: 'Проверки характеристик',
                article_version_id: TEXT_VERSION
            }
        ]
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

test('Чтение собирает главы и закреплённый текст в порядке оглавления', () => {
    const book = parseBookReading(reading(), BOOK, VERSION);

    assert.equal(book.title, 'Основные правила');
    assert.equal(book.version, 1);
    assert.equal(book.sections[0].title, 'Основы');
    assert.equal(book.sections[1].parentKey, 'basics');
    assert.equal(book.sections[1].title, 'Проверки характеристик');
    assert.equal(book.sections[1].body, 'Текст правила');
});

test('Ответ другой публикации не принимается', () => {
    const payload = reading();
    payload.publication.id = TEXT_VERSION;

    assert.throws(() => parseBookReading(payload, BOOK, VERSION), TypeError);
});

test('Отсутствующий закреплённый текст не превращается в пустой раздел', () => {
    const payload = reading();
    payload.articles = [];

    assert.throws(() => parseBookReading(payload, BOOK, VERSION), TypeError);
});

test('Повторяющиеся ключи оглавления отклоняются', () => {
    const payload = reading();
    payload.toc[1].key = payload.toc[0].key;

    assert.throws(() => parseBookReading(payload, BOOK, VERSION), TypeError);
});

test('Неверная глубина оглавления отклоняется', () => {
    const payload = reading();
    payload.toc[1].depth = 0;

    assert.throws(() => parseBookReading(payload, BOOK, VERSION), TypeError);
});

test('Несуществующая родительская глава отклоняется', () => {
    const payload = reading();
    payload.toc[1].parent_key = 'missing';

    assert.throws(() => parseBookReading(payload, BOOK, VERSION), TypeError);
});

test('Загрузчик получает конкретную публикацию и сигнал отмены', async () => {
    const calls = [];
    const states = [];
    const reader = createBookReader({
        loadBook: async (...args) => {
            calls.push(args);
            return reading();
        },
        onChange: (state) => states.push(state)
    });

    await reader.open(BOOK, VERSION);

    assert.equal(calls[0][0], BOOK);
    assert.equal(calls[0][1], VERSION);
    assert.ok(calls[0][2].signal instanceof AbortSignal);
    assert.equal(states[0].loading, true);
    assert.equal(states.at(-1).loading, false);
    assert.equal(states.at(-1).book.title, 'Основные правила');
});

test('Закрытая книга не открывается снова из-за запоздавшего ответа', async () => {
    const response = deferred();
    const states = [];
    let signal;
    const reader = createBookReader({
        loadBook: (_book, _version, options) => {
            signal = options.signal;
            return response.promise;
        },
        onChange: (state) => states.push(state)
    });

    const pending = reader.open(BOOK, VERSION);
    reader.close();
    response.resolve(reading());
    await pending;

    assert.equal(signal.aborted, true);
    assert.equal(states.at(-1).opened, false);
    assert.equal(states.at(-1).book, null);
});

test('Поздний ответ предыдущего открытия не заменяет новый', async () => {
    const response = deferred();
    const states = [];
    let calls = 0;
    const reader = createBookReader({
        loadBook: async () => {
            calls += 1;
            return calls === 1 ? response.promise : reading('Актуальное открытие');
        },
        onChange: (state) => states.push(state)
    });

    const old = reader.open(BOOK, VERSION);
    await reader.open(BOOK, VERSION);
    response.resolve(reading('Запоздавший ответ'));
    await old;

    assert.equal(states.at(-1).book.title, 'Актуальное открытие');
});

test('Ошибка авторизации предлагает повторный вход без частичного текста', async () => {
    const states = [];
    const reader = createBookReader({
        loadBook: async () => {
            throw Object.assign(new Error('Unauthorized'), { status: 401 });
        },
        onChange: (state) => states.push(state)
    });

    await reader.open(BOOK, VERSION);

    assert.equal(states.at(-1).status, 401);
    assert.equal(states.at(-1).book, null);
    assert.equal(states.at(-1).loading, false);
});

test('После уничтожения загрузчик больше не вызывается', async () => {
    let calls = 0;
    const reader = createBookReader({
        loadBook: async () => {
            calls += 1;
            return reading();
        }
    });

    reader.dispose();
    await reader.open(BOOK, VERSION);

    assert.equal(calls, 0);
});
