// tests/js/rules/rules-catalog.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createRulesCatalogController, parseCatalogPage } from '../../../frontend/src/js/features/rules/catalog-controller.js';

const FIRST = '11111111-1111-4111-8111-111111111111';
const SECOND = '22222222-2222-4222-8222-222222222222';
const VERSION = '33333333-3333-4333-8333-333333333333';

function card(id = FIRST, title = 'Проверки') {
    return {
        id,
        slug: 'checks',
        visibility: 'public',
        is_owned: false,
        version_id: VERSION,
        version_number: 1,
        published_at: '2026-11-12T12:00:00Z',
        title,
        summary: 'Описание',
        edition_key: null,
        language: 'ru'
    };
}

function page(items, nextAfter = null) {
    return { items, next_after: nextAfter };
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((done, fail) => {
        resolve = done;
        reject = fail;
    });

    return { promise, resolve, reject };
}

test('Начальная загрузка передаёт вид, режим и размер страницы', async () => {
    const calls = [];
    const controller = createRulesCatalogController({
        loadPage: async (...args) => {
            calls.push(args);
            return page([card()]);
        }
    });

    await controller.reload();

    assert.equal(calls[0][0], 'books');
    assert.deepEqual(calls[0][1], { scope: 'available', limit: 30 });
    assert.ok(calls[0][2].signal instanceof AbortSignal);
    assert.equal(controller.getState().items.length, 1);
    assert.equal(controller.getState().loading, false);
});

test('Смена фильтров начинает новый каталог книг', async () => {
    const calls = [];
    const controller = createRulesCatalogController({
        loadPage: async (...args) => {
            calls.push(args);
            return page([card()]);
        }
    });

    await controller.reload();
    await controller.reload({ kind: 'books', scope: 'mine', q: '  Бой  ', edition_key: '2014', language: 'ru' });

    assert.equal(calls[1][0], 'books');
    assert.deepEqual(calls[1][1], { scope: 'mine', q: 'Бой', edition_key: '2014', language: 'ru', limit: 30 });
    assert.equal(controller.getState().items.length, 1);
});

test('Продолжение использует курсор и убирает повтор карточки', async () => {
    const calls = [];
    const responses = [page([card()], FIRST), page([card(), card(SECOND)])];
    const controller = createRulesCatalogController({
        loadPage: async (...args) => {
            calls.push(args);
            return responses.shift();
        }
    });

    await controller.reload();
    await controller.next();

    assert.equal(calls[1][1].after, FIRST);
    assert.deepEqual(controller.getState().items.map((item) => item.id), [FIRST, SECOND]);
    assert.equal(controller.getState().nextAfter, null);
});

test('Запоздавший ответ не заменяет новый поиск', async () => {
    const old = deferred();
    let previousSignal;
    const controller = createRulesCatalogController({
        loadPage: async (kind, filters, options) => {
            if (filters.q === 'старый') {
                previousSignal = options.signal;
                return old.promise;
            }

            return page([card(SECOND, 'Новый результат')]);
        }
    });

    const pending = controller.reload({ q: 'старый' });
    await controller.reload({ q: 'новый' });

    assert.equal(previousSignal.aborted, true);
    old.resolve(page([card(FIRST, 'Старый результат')]));
    await pending;

    assert.equal(controller.getState().items[0].title, 'Новый результат');
    assert.equal(controller.getState().filters.q, 'новый');
});

test('Ошибка продолжения сохраняет уже загруженные карточки', async () => {
    let calls = 0;
    const controller = createRulesCatalogController({
        loadPage: async () => {
            calls += 1;

            if (calls > 1) throw new Error('Соединение прервано');

            return page([card()], FIRST);
        }
    });

    await controller.reload();
    await controller.next();

    assert.equal(controller.getState().items.length, 1);
    assert.equal(controller.getState().nextAfter, FIRST);
    assert.equal(controller.getState().error, 'Соединение прервано');
    assert.equal(controller.getState().loading, false);
});

test('Двойное нажатие продолжения не создаёт параллельные запросы', async () => {
    const continuation = deferred();
    let calls = 0;
    const controller = createRulesCatalogController({
        loadPage: async () => {
            calls += 1;
            return calls === 1 ? page([card()], FIRST) : continuation.promise;
        }
    });

    await controller.reload();
    const pending = controller.next();
    await controller.next();

    assert.equal(calls, 2);
    continuation.resolve(page([card(SECOND)]));
    await pending;
});

test('Повторяющийся курсор не вызывает бесконечное продолжение', async () => {
    const controller = createRulesCatalogController({ loadPage: async () => page([card()], FIRST) });

    await controller.reload();
    await controller.next();

    assert.match(controller.getState().error, /повторил продолжение/u);
    assert.equal(controller.getState().items.length, 1);
});

test('Ошибка авторизации сохраняет HTTP-статус для приглашения войти', async () => {
    const controller = createRulesCatalogController({
        loadPage: async () => {
            throw Object.assign(new Error('Сессия завершена'), { status: 401 });
        }
    });

    await controller.reload();

    assert.equal(controller.getState().status, 401);
    assert.equal(controller.getState().loading, false);
});

test('После уничтожения контроллера ответ не обновляет представление', async () => {
    const response = deferred();
    const states = [];
    const controller = createRulesCatalogController({
        loadPage: () => response.promise,
        onChange: (state) => states.push(state)
    });

    const pending = controller.reload();
    controller.dispose();
    response.resolve(page([card()]));
    await pending;

    assert.equal(states.length, 1);
});

test('Некорректные фильтры отклоняются до отправки', () => {
    const controller = createRulesCatalogController({
        loadPage: async () => assert.fail('Запрос не должен отправляться')
    });

    assert.throws(() => controller.reload({ kind: 'unknown' }), TypeError);
    assert.throws(() => controller.reload({ scope: 'all' }), TypeError);
    assert.throws(() => controller.reload({ language: 'r' }), TypeError);
    assert.throws(() => controller.reload({ q: 'a'.repeat(101) }), TypeError);
    assert.throws(() => controller.reload({ owner_id: FIRST }), TypeError);
});

test('Некорректная страница не принимается как успешный результат', () => {
    assert.throws(() => parseCatalogPage({ items: null, next_after: null }), TypeError);
    assert.throws(() => parseCatalogPage(page([], FIRST)), TypeError);
    assert.throws(() => parseCatalogPage(page([card()], SECOND)), TypeError);
    assert.throws(() => parseCatalogPage(page([{ ...card(), version_id: '../other' }])), TypeError);
});

test('Полученное состояние нельзя использовать для изменения внутреннего списка', async () => {
    const controller = createRulesCatalogController({ loadPage: async () => page([card()]) });

    await controller.reload();

    const state = controller.getState();
    state.items[0].title = 'Подмена';
    state.filters.kind = 'books';

    assert.equal(controller.getState().items[0].title, 'Проверки');
    assert.equal(controller.getState().filters.kind, 'articles');
});
