import test from 'node:test';
import assert from 'node:assert/strict';

import {loadBookPublications} from '../../frontend/src/js/features/game-systems/book/book-publications-data.js';

function item(number) {
    return {
        id: `publication-${number}`,
        system_id: 'system-one',
        version_number: number,
        rules_engine_version: '1.0',
        published_at: '2026-11-06T08:00:00Z'
    };
}

function load(request, options = {}) {
    return loadBookPublications({request, systemId: 'system-one', manager: true, ...options});
}

test('История управляющего использует административный маршрут', async () => {
    const paths = [];

    const request = async (path) => {
        paths.push(path);
        return {items: [item(3), item(2)], next_before: 2};
    };

    const page = await load(request);

    assert.deepEqual(paths, ['/admin/game-systems/system-one/rules/versions?limit=20']);
    assert.equal(page.next_before, 2);
});

test('Обычный просмотр и продолжение используют публичный маршрут и границу', async () => {
    let path;

    await load(async (value) => {
        path = value;
        return {items: [item(1)], next_before: null};
    }, {manager: false, before: 2});

    assert.equal(path, '/game-systems/items/system-one/rules/versions?limit=20&before=2');
});

test('Пустая история является корректным результатом', async () => {
    const page = await load(async () => ({items: [], next_before: null}));

    assert.deepEqual(page, {items: [], next_before: null});
});

test('История другой системы не принимается', async () => {
    const wrong = {...item(3), system_id: 'other-system'};

    await assert.rejects(
        () => load(async () => ({items: [wrong], next_before: null})),
        /другой игровой системе/u
    );
});

test('Нарушенный порядок и повторы отклоняются', async () => {
    for (const items of [[item(2), item(3)], [item(3), item(3)]]) {
        await assert.rejects(() => load(async () => ({items, next_before: null})), /порядок|повторяется/u);
    }
});

test('Продолжение не может вернуть уже пройденную границу', async () => {
    await assert.rejects(
        () => load(async () => ({items: [item(3)], next_before: null}), {before: 3}),
        /порядок/u
    );
});

test('Некорректная граница продолжения и отсутствие поля отклоняются', async () => {
    const pages = [
        {items: [item(3)], next_before: 2},
        {items: [], next_before: 1},
        {items: [item(3)]}
    ];

    for (const page of pages) {
        await assert.rejects(() => load(async () => page), /продолжени/u);
    }
});

test('Ошибка запроса не маскируется пустой историей', async () => {
    await assert.rejects(() => load(async () => {
        throw new Error('Нет соединения');
    }), /Нет соединения/u);
});

test('Полученная история не разделяет объекты с ответом запроса', async () => {
    const raw = {items: [item(3)], next_before: null};
    const result = await load(async () => raw);

    result.items[0].rules_engine_version = 'changed';

    assert.equal(raw.items[0].rules_engine_version, '1.0');
});
