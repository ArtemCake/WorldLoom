// tests/js/rules/rules-book-create.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { NEW_BOOK_DEFAULTS, newBookPayload } from '../../../frontend/src/js/features/rules/books/book-create-data.js';
import { createBookCreation } from '../../../frontend/src/js/features/rules/books/book-create-state.js';

const SYSTEM = randomUUID();
const BOOK = randomUUID();

function setup({ create, openBook } = {}) {
    const writes = [];
    const reads = [];
    const api = {
        async create(payload) {
            writes.push(structuredClone(payload));
            if (create) return create(payload);

            return {
                book: { id: BOOK, system_id: payload.system_id },
                draft: { book_id: BOOK, revision: 1 }
            };
        }
    };

    const creation = createBookCreation({
        api,
        makeSlug: () => 'book-test',
        openBook: async (bookId) => {
            reads.push(bookId);
            if (openBook) return openBook(bookId);
        }
    });

    creation.open(SYSTEM);
    creation.change('title', 'Книга правил');

    return { creation, writes, reads };
}

test('Создаётся закрытая книга правил с пустым оглавлением', () => {
    const values = { ...NEW_BOOK_DEFAULTS, system_id: SYSTEM, title: ' Правила ' };
    const payload = newBookPayload(values, 'book-test');

    assert.equal(payload.system_id, SYSTEM);
    assert.equal(payload.visibility, 'private');
    assert.equal(payload.content.title, 'Правила');
    assert.equal(payload.content.category, 'rules');
    assert.equal(payload.content.schema_version, 1);
    assert.equal(payload.content.edition_key, null);
    assert.deepEqual(payload.content.sources, []);
    assert.deepEqual(payload.content.toc, []);
    assert.equal(values.title, ' Правила ');
});

test('Все системы и пустое название не подходят для создания', () => {
    const values = { ...NEW_BOOK_DEFAULTS, system_id: SYSTEM, title: 'Книга' };

    assert.throws(() => newBookPayload({ ...values, system_id: '' }, 'book-test'), TypeError);
    assert.throws(() => newBookPayload({ ...values, title: '   ' }, 'book-test'), TypeError);
    assert.throws(() => newBookPayload({ ...values, language: 'r' }, 'book-test'), TypeError);
});

test('После создания открывается именно новая книга', async () => {
    const { creation, writes, reads } = setup();

    assert.equal(creation.getState().needsGuard, true);
    assert.equal(await creation.submit(), BOOK);
    assert.equal(writes.length, 1);
    assert.deepEqual(reads, [BOOK]);
    assert.equal(creation.getState().opened, false);
    assert.equal(creation.getState().needsGuard, false);
});

test('Некорректные поля не отправляются на сервер', async () => {
    const { creation, writes } = setup();

    creation.change('title', ' ');
    assert.equal(await creation.submit(), null);
    assert.equal(writes.length, 0);
    assert.equal(creation.getState().blocked, false);
    assert.ok(creation.getState().error);
});

test('Повторное нажатие во время POST не создаёт вторую книгу', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const { creation, writes } = setup({ create: () => pending });

    const first = creation.submit();

    assert.equal(creation.getState().busy, true);
    assert.equal(await creation.submit(), null);
    assert.equal(creation.close(), false);
    assert.equal(creation.change('title', 'Другое название'), false);

    finish({ book: { id: BOOK, system_id: SYSTEM }, draft: { book_id: BOOK, revision: 1 } });
    assert.equal(await first, BOOK);
    assert.equal(writes.length, 1);
});

test('Во время открытия созданной книги повторная отправка также заблокирована', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const { creation, writes } = setup({ openBook: () => pending });

    const first = creation.submit();
    await Promise.resolve();
    await Promise.resolve();

    assert.equal(creation.getState().busy, true);
    assert.equal(await creation.submit(), null);
    assert.equal(writes.length, 1);

    finish();
    await first;
});

test('Подтверждённая ошибка запроса оставляет форму доступной для исправления', async () => {
    const { creation, writes } = setup({
        create() {
            throw Object.assign(new Error('Проверьте данные'), { status: 422, uncertain: false });
        }
    });

    await creation.submit();

    assert.equal(creation.getState().blocked, false);
    assert.equal(creation.getState().values.title, 'Книга правил');
    assert.equal(creation.change('title', 'Исправленная книга'), true);
    assert.equal(writes.length, 1);
});

test('Отказ доступа не запускает открытие черновика', async () => {
    const { creation, reads } = setup({
        create() {
            throw Object.assign(new Error('Недостаточно прав'), { status: 403, uncertain: false });
        }
    });

    await creation.submit();

    assert.equal(creation.getState().bookId, null);
    assert.equal(creation.getState().error, 'Недостаточно прав');
    assert.deepEqual(reads, []);
});

test('Неопределённый результат блокирует новый POST даже после закрытия формы', async () => {
    const { creation, writes } = setup({
        create() {
            throw Object.assign(new Error('Ответ потерян'), { uncertain: true });
        }
    });

    await creation.submit();

    assert.equal(creation.getState().blocked, true);
    assert.equal(creation.getState().values.title, 'Книга правил');
    assert.equal(await creation.submit(), null);

    creation.close();
    creation.open(SYSTEM);
    assert.equal(await creation.submit(), null);
    assert.equal(writes.length, 1);
});

test('Некорректное подтверждение сервера не вызывает повторное создание', async () => {
    const { creation, writes, reads } = setup({
        create() {
            return { book: { id: BOOK, system_id: randomUUID() }, draft: { book_id: BOOK, revision: 1 } };
        }
    });

    await creation.submit();
    await creation.submit();

    assert.equal(creation.getState().blocked, true);
    assert.equal(writes.length, 1);
    assert.deepEqual(reads, []);
});

test('При ошибке открытия повторяется только GET, без нового создания', async () => {
    let attempts = 0;
    const { creation, writes, reads } = setup({
        openBook() {
            attempts += 1;
            if (attempts === 1) throw new Error('Редактор временно недоступен');
        }
    });

    assert.equal(await creation.submit(), null);
    assert.equal(creation.getState().bookId, BOOK);
    assert.equal(creation.getState().blocked, false);
    assert.equal(creation.getState().opened, true);

    assert.equal(await creation.submit(), BOOK);
    assert.equal(writes.length, 1);
    assert.deepEqual(reads, [BOOK, BOOK]);
});

test('После успешного завершения можно начать следующую книгу', async () => {
    const { creation } = setup();
    await creation.submit();

    creation.open(SYSTEM);

    assert.equal(creation.getState().bookId, null);
    assert.equal(creation.getState().values.title, '');
    assert.equal(creation.getState().values.system_id, SYSTEM);
    assert.equal(creation.getState().dirty, false);
});

test('Полученный снимок не изменяет внутренние поля формы', () => {
    const { creation } = setup();
    const snapshot = creation.getState();

    snapshot.values.title = 'Подмена';

    assert.equal(creation.getState().values.title, 'Книга правил');
});

test('После уничтожения формы ответ POST не открывает редактор', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const { creation, reads } = setup({ create: () => pending });

    const submitted = creation.submit();
    creation.dispose();

    finish({ book: { id: BOOK, system_id: SYSTEM }, draft: { book_id: BOOK, revision: 1 } });
    await submitted;

    assert.deepEqual(reads, []);
});
