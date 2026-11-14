// tests/js/rules/rules-draft-toc-data.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { applyChapterCommand, validateBookToc } from '../../../frontend/src/js/features/rules/draft/draft-toc-data.js';

const VERSION = '33333333-3333-4333-8333-333333333333';

function chapter(key = 'main', parent = null, position = 0) {
    return { kind: 'chapter', key, parent_key: parent, position, title: key };
}

function article(parent = 'main', position = 0) {
    return {
        kind: 'article',
        key: 'text',
        parent_key: parent,
        position,
        title: null,
        article_version_id: VERSION
    };
}

test('Создание корневой главы не изменяет исходный массив', () => {
    const source = [chapter()];
    const result = applyChapterCommand(source, {
        type: 'add', key: 'second', parent_key: null, title: 'Вторая глава'
    });

    assert.equal(source.length, 1);
    assert.equal(result.length, 2);
    assert.equal(result[1].position, 1);
    assert.equal(result[1].parent_key, null);
});

test('Новая подглава добавляется после всех существующих детей', () => {
    const source = [chapter(), article('main', 7)];
    const result = applyChapterCommand(source, {
        type: 'add', key: 'child', parent_key: 'main', title: 'Подглава'
    });

    assert.equal(result.at(-1).position, 8);
    assert.deepEqual(result[1], source[1]);
});

test('Переименование сохраняет ключ, положение и закреплённые разделы', () => {
    const source = [chapter(), article()];
    const result = applyChapterCommand(source, { type: 'rename', key: 'main', title: 'Основы' });

    assert.equal(result[0].title, 'Основы');
    assert.equal(result[0].key, 'main');
    assert.equal(result[0].position, 0);
    assert.deepEqual(result[1], source[1]);
    assert.equal(source[0].title, 'main');
});

test('Глава перемещается относительно статьи без замены её публикации', () => {
    const source = [article(null, 2), chapter('main', null, 5)];
    const result = applyChapterCommand(source, { type: 'move', key: 'main', delta: -1 });

    assert.equal(result[0].position, 5);
    assert.equal(result[1].position, 2);
    assert.equal(result[0].article_version_id, VERSION);
    assert.equal(result[0].title, null);
    assert.equal(source[0].position, 2);
});

test('Дети перемещаемой главы сохраняют родителя и позиции', () => {
    const source = [chapter(), chapter('second', null, 10), article()];
    const result = applyChapterCommand(source, { type: 'move', key: 'main', delta: 1 });

    assert.equal(result[0].position, 10);
    assert.equal(result[1].position, 0);
    assert.deepEqual(result[2], source[2]);
});

test('Перемещение за границу уровня ничего не меняет', () => {
    const source = [chapter(), article()];
    const result = applyChapterCommand(source, { type: 'move', key: 'main', delta: -1 });

    assert.deepEqual(result, source);
});

test('Пустая глава удаляется, остальные пункты не перенумеровываются', () => {
    const source = [chapter(), chapter('second', null, 10)];
    const result = applyChapterCommand(source, { type: 'remove', key: 'main' });

    assert.deepEqual(result, [source[1]]);
    assert.equal(source.length, 2);
});

test('Глава с разделом или подглавой не удаляется', () => {
    for (const child of [article(), chapter('child', 'main')]) {
        const source = [chapter(), child];
        assert.throws(() => applyChapterCommand(source, { type: 'remove', key: 'main' }), /пустую/u);
        assert.equal(source.length, 2);
    }
});

test('Команды глав не позволяют изменять статьи', () => {
    const source = [chapter(), article()];

    for (const type of ['remove', 'rename', 'move']) {
        assert.throws(() => applyChapterCommand(source, { type, key: 'text', title: 'Другое', delta: 1 }), TypeError);
    }
});

test('Пустое название и повтор ключа отклоняются без изменения исходника', () => {
    const source = [chapter()];

    assert.throws(() => applyChapterCommand(source, { type: 'rename', key: 'main', title: ' ' }), TypeError);
    assert.throws(() => applyChapterCommand(source, {
        type: 'add', key: 'main', parent_key: null, title: 'Повтор'
    }), TypeError);

    assert.deepEqual(source, [chapter()]);
});

test('Проверяются позиции, родители, ключи и ссылки публикаций', () => {
    const invalid = [
        [chapter(), chapter('second')],
        [chapter('orphan', 'missing')],
        [chapter('bad key')],
        [{ ...article(null), article_version_id: 'invalid' }],
        [article(null), chapter('child', 'text')],
        [chapter('main', 'child'), chapter('child', 'main')]
    ];

    for (const toc of invalid) {
        assert.throws(() => validateBookToc(toc), TypeError);
    }
});

test('Разрешены 32 уровня, но не 33', () => {
    const source = Array.from({ length: 32 }, (_, index) => {
        return chapter(`level-${index}`, index === 0 ? null : `level-${index - 1}`);
    });

    assert.equal(validateBookToc(source).length, 32);
    assert.throws(() => applyChapterCommand(source, {
        type: 'add', key: 'too-deep', parent_key: 'level-31', title: 'Лишний уровень'
    }), /32/u);
    assert.equal(source.length, 32);
});

test('Ограничение числа пунктов проверяется до принятия новой структуры', () => {
    const source = Array.from({ length: 2000 }, (_, index) => chapter(`chapter-${index}`, null, index));

    assert.equal(validateBookToc(source).length, 2000);
    assert.throws(() => applyChapterCommand(source, {
        type: 'add', key: 'extra', parent_key: null, title: 'Лишняя глава'
    }), /2000/u);
    assert.equal(source.length, 2000);
});
