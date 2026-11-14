// tests/js/rules/rules-draft-section-data.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { applySectionCommand, readSectionVersion } from '../../../frontend/src/js/features/rules/draft/draft-section-data.js';

const ARTICLE = '11111111-1111-4111-8111-111111111111';
const VERSION = '22222222-2222-4222-8222-222222222222';
const OTHER = '33333333-3333-4333-8333-333333333333';

function publication() {
    return {
        id: VERSION,
        article_id: ARTICLE,
        version_number: 2,
        content_json: {
            schema_version: 1,
            title: 'Проверки',
            body: 'Текст правила',
            sources: [{ title: 'Источник' }]
        }
    };
}

function chapter(key = 'main', parent = null, position = 0) {
    return { kind: 'chapter', key, parent_key: parent, position, title: key };
}

function attach(key = 'checks', parent = 'main') {
    return { type: 'attach', key, parent_key: parent, publication: publication() };
}

test('Добавляется конкретная публикация, исходное оглавление не меняется', () => {
    const source = [chapter()];
    const result = applySectionCommand(source, attach());

    assert.equal(source.length, 1);
    assert.equal(result[1].kind, 'article');
    assert.equal(result[1].article_version_id, VERSION);
    assert.equal(result[1].title, 'Проверки');
    assert.equal(result[1].parent_key, 'main');
    assert.equal(Object.hasOwn(result[1], 'body'), false);
    assert.equal(Object.hasOwn(result[1], 'sources'), false);
});

test('Поддерживается добавление в корень книги', () => {
    const result = applySectionCommand([], attach('checks', null));

    assert.equal(result[0].parent_key, null);
    assert.equal(result[0].position, 0);
});

test('Одна публикация может встречаться в разных пунктах', () => {
    const first = applySectionCommand([chapter()], attach());
    const second = applySectionCommand(first, attach('checks-again'));

    assert.equal(second[1].article_version_id, second[2].article_version_id);
    assert.notEqual(second[1].key, second[2].key);
    assert.equal(second[2].position, 1);
});

test('Повтор ключа и отсутствующая глава отклоняются', () => {
    assert.throws(() => applySectionCommand([chapter()], attach('main')), TypeError);
    assert.throws(() => applySectionCommand([], attach()), TypeError);
});

test('Раздел нельзя сделать родителем другого раздела', () => {
    const source = applySectionCommand([], attach('checks', null));

    assert.throws(() => applySectionCommand(source, attach('child', 'checks')), TypeError);
});

test('Удаление пункта не удаляет другие вхождения публикации', () => {
    const first = applySectionCommand([], attach('first', null));
    const source = applySectionCommand(first, attach('second', null));
    const result = applySectionCommand(source, { type: 'remove', key: 'first' });

    assert.equal(source.length, 2);
    assert.equal(result.length, 1);
    assert.equal(result[0].key, 'second');
    assert.equal(result[0].article_version_id, VERSION);
});

test('Раздел перемещается относительно главы без замены публикации', () => {
    const source = applySectionCommand([chapter()], attach('checks', null));
    const result = applySectionCommand(source, { type: 'move', key: 'checks', delta: -1 });

    assert.equal(result[0].position, 1);
    assert.equal(result[1].position, 0);
    assert.equal(result[1].article_version_id, VERSION);
    assert.equal(source[1].position, 1);
});

test('Команды разделов не изменяют главы', () => {
    assert.throws(() => applySectionCommand([chapter()], { type: 'remove', key: 'main' }), TypeError);
});

test('Чужая публикация и пустой текст предпросмотра не принимаются', () => {
    assert.throws(() => readSectionVersion(publication(), ARTICLE, OTHER), TypeError);

    const empty = publication();
    empty.content_json.body = ' ';
    assert.throws(() => readSectionVersion(empty, ARTICLE, VERSION), TypeError);
});

test('Добавление за допустимую глубину не изменяет исходник', () => {
    const source = Array.from({ length: 32 }, (_, index) => {
        return chapter(`level-${index}`, index === 0 ? null : `level-${index - 1}`);
    });

    assert.throws(() => applySectionCommand(source, attach('too-deep', 'level-31')), TypeError);
    assert.equal(source.length, 32);
});
