import test from 'node:test';
import assert from 'node:assert/strict';

import * as source from '../../frontend/src/js/features/game-systems/book/book-publication-source.js';

function publication() {
    return {
        id: 'publication-one',
        system_id: 'system-one',
        version_number: 2,
        rules_engine_version: '1.0',
        published_at: '2026-11-06T08:00:00Z',
        rules: {
            schema_version: 4,
            calculations: {attributes: {}, derived: {}},
            initial_attributes: {},
            resources: {}
        }
    };
}

test('Без выбранного снимка сохраняется просмотр последней публикации', () => {
    assert.equal(source.selectedBookPublication('?source=published', 'view'), null);
});

test('Конкретный снимок допускается только в режиме просмотра', () => {
    assert.equal(source.selectedBookPublication('?version=publication-one', 'view'), 'publication-one');

    assert.throws(() => source.selectedBookPublication('?version=publication-one', 'edit'), /просмотра/u);
    assert.throws(() => source.selectedBookPublication('?version=publication-one', 'create'), /просмотра/u);
});

test('Пустое и неоднозначное указание версии отклоняются', () => {
    assert.throws(() => source.selectedBookPublication('?version=', 'view'), /идентификатор/u);
    assert.throws(() => source.selectedBookPublication('?version=one&version=two', 'view'), /несколько/u);
});

test('Постоянная ссылка содержит выбранный снимок и кодирует значения', () => {
    const href = source.bookPublicationHref('system/one', 'publication?one');

    assert.equal(
        href,
        '/game-systems/catalog/system%2Fone?source=published&version=publication%3Fone'
    );
});

test('Управляющий читает конкретную публикацию через административный маршрут', async () => {
    const calls = [];

    const request = async (path) => {
        calls.push(path);
        return publication();
    };

    const result = await source.loadBookPublishedRules({
        request,
        systemId: 'system-one',
        manager: true,
        versionId: 'publication-one'
    });

    assert.deepEqual(calls, ['/admin/game-systems/system-one/rules/versions/publication-one']);
    assert.equal(result.version.id, 'publication-one');
});

test('Обычный просмотр использует маршрут опубликованных правил активной системы', async () => {
    const calls = [];

    const request = async (path) => {
        calls.push(path);
        return publication();
    };

    await source.loadBookPublishedRules({
        request,
        systemId: 'system-one',
        manager: false,
        versionId: 'publication-one'
    });

    assert.deepEqual(calls, ['/game-systems/items/system-one/rules/versions/publication-one']);
});

test('Последняя публикация сохраняет существующий формат ответа', async () => {
    const calls = [];

    const request = async (path) => {
        calls.push(path);
        return {version: publication()};
    };

    const result = await source.loadBookPublishedRules({
        request,
        systemId: 'system-one',
        manager: true
    });

    assert.deepEqual(calls, ['/admin/game-systems/system-one/rules/latest']);
    assert.equal(result.version.version_number, 2);
});

test('Отсутствие последней публикации не считается ошибкой', async () => {
    const result = await source.loadBookPublishedRules({
        request: async () => ({version: null}),
        systemId: 'system-one',
        manager: false
    });

    assert.deepEqual(result, {version: null});
});

test('Ошибка конкретного снимка не вызывает загрузку последнего', async () => {
    let calls = 0;

    const request = async () => {
        calls += 1;
        throw Object.assign(new Error('Публикация не найдена'), {status: 404});
    };

    await assert.rejects(() => source.loadBookPublishedRules({
        request,
        systemId: 'system-one',
        manager: true,
        versionId: 'publication-one'
    }), /не найдена/u);

    assert.equal(calls, 1);
});

test('Ответ с другой публикацией или другой системой не принимается', async () => {
    for (const replacement of [{id: 'another-publication'}, {system_id: 'another-system'}]) {
        const request = async () => ({...publication(), ...replacement});

        await assert.rejects(() => source.loadBookPublishedRules({
            request,
            systemId: 'system-one',
            manager: true,
            versionId: 'publication-one'
        }), /друг/u);
    }
});

test('Возвращённый снимок не разделяет вложенные объекты с ответом запроса', async () => {
    const raw = publication();

    const result = await source.loadBookPublishedRules({
        request: async () => raw,
        systemId: 'system-one',
        manager: true,
        versionId: 'publication-one'
    });

    result.version.rules.initial_attributes.changed = 10;

    assert.deepEqual(raw.rules.initial_attributes, {});
});
