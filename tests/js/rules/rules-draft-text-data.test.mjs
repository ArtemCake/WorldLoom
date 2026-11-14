// tests/js/rules/rules-draft-text-data.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { applyBookTextCommand } from '../../../frontend/src/js/features/rules/draft/draft-text-data.js';
import { applyChapterCommand, readBookTextContent, validateBookToc } from '../../../frontend/src/js/features/rules/draft/draft-toc-data.js';
import { applySectionCommand } from '../../../frontend/src/js/features/rules/draft/draft-section-data.js';

const ARTICLE = randomUUID();
const VERSION = randomUUID();

function ownText(key = 'checks', parent = 'main', position = 0) {
    return {
        kind: 'text',
        key,
        parent_key: parent,
        position,
        title: 'Проверки в оглавлении',
        content: {
            schema_version: 1,
            title: 'Проверки характеристик',
            summary: 'Краткое описание',
            body: 'Первая редакция.',
            language: 'ru',
            edition_key: '2014',
            audience: 'gm',
            rule_kind: 'homebrew',
            sources: [{ title: 'Источник', locator: 'Раздел 2', attribution: 'Авторский текст' }]
        }
    };
}

function toc() {
    return [
        { kind: 'chapter', key: 'main', parent_key: null, position: 0, title: 'Основы' },
        ownText(),
        {
            kind: 'article',
            key: 'external',
            parent_key: 'main',
            position: 1,
            title: null,
            article_version_id: VERSION
        }
    ];
}

test('Смешанное оглавление проходит проверку и возвращается независимой копией', () => {
    const source = toc();
    const checked = validateBookToc(source);

    assert.deepEqual(checked, source);
    checked[1].content.sources[0].title = 'Локальное изменение';
    assert.equal(source[1].content.sources[0].title, 'Источник');
});

test('Пустой текст допустим в рабочем черновике', () => {
    const source = toc();
    source[1].content.body = '';

    assert.doesNotThrow(() => validateBookToc(source));
});

test('Минимальное содержание получает значения серверных полей по умолчанию', () => {
    const source = { title: 'Новый текст' };
    const checked = readBookTextContent(source);

    assert.equal(checked.schema_version, 1);
    assert.equal(checked.body, '');
    assert.equal(checked.language, 'ru');
    assert.equal(checked.edition_key, null);
    assert.equal(checked.audience, 'both');
    assert.equal(checked.rule_kind, 'base');
    assert.deepEqual(checked.sources, []);
    assert.deepEqual(source, { title: 'Новый текст' });
});

test('Добавление не меняет исходное оглавление и данные команды', () => {
    const source = toc();
    const node = ownText('new-text', null, 1);
    const before = structuredClone(node);
    const result = applyBookTextCommand(source, { type: 'add', node });

    assert.equal(source.length, 3);
    assert.equal(result.length, 4);
    assert.deepEqual(node, before);

    result.at(-1).content.body = 'Локальная правка';
    assert.equal(node.content.body, before.content.body);
});

test('Обновление меняет только содержание выбранного текста', () => {
    const source = toc();
    const content = { ...structuredClone(source[1].content), body: 'Новая редакция.' };
    const result = applyBookTextCommand(source, { type: 'update', key: 'checks', content });

    assert.deepEqual(result[0], source[0]);
    assert.deepEqual(result[2], source[2]);
    assert.deepEqual(result[1], { ...source[1], content });
    assert.equal(source[1].content.body, 'Первая редакция.');
    assert.equal(result[1].title, 'Проверки в оглавлении');

    result[1].content.sources[0].locator = 'Другой раздел';
    assert.equal(content.sources[0].locator, 'Раздел 2');
});

test('Удаление собственного текста не удаляет главу и внешнюю ссылку', () => {
    const source = toc();
    const result = applyBookTextCommand(source, { type: 'remove', key: 'checks' });

    assert.deepEqual(result, [source[0], source[2]]);
    assert.equal(source.length, 3);
});

test('Команды собственного текста не применяются к главе или внешней статье', () => {
    for (const key of ['main', 'external', 'missing']) {
        assert.throws(() => applyBookTextCommand(toc(), { type: 'remove', key }), TypeError);
        const command = { type: 'update', key, content: ownText().content };
        assert.throws(() => applyBookTextCommand(toc(), command), TypeError);
    }
});

test('Повтор ключа, занятая позиция и некорректный родитель отклоняются', () => {
    const duplicate = ownText('checks', null, 1);
    const occupied = ownText('next', 'main', 1);
    const missing = ownText('next', 'missing', 0);
    const leaf = ownText('next', 'checks', 0);

    for (const node of [duplicate, occupied, missing, leaf]) {
        assert.throws(() => applyBookTextCommand(toc(), { type: 'add', node }), TypeError);
    }
});

test('Собственный текст нельзя подменить ссылкой на публикацию', () => {
    const source = toc();
    source[1].article_version_id = VERSION;

    assert.throws(() => validateBookToc(source), TypeError);
});

test('Проверяются поля содержания, источники и допустимая длина', () => {
    const invalid = [
        { title: ' ' },
        { body: 42 },
        { schema_version: 2 },
        { language: 'r' },
        { edition_key: '' },
        { audience: 'unknown' },
        { rule_kind: 'unknown' },
        { body: 'а'.repeat(300001) },
        { sources: [{ title: 'Источник', url: 'javascript:alert(1)' }] },
        { sources: [{ title: 'Источник', publisher: 42 }] },
        { sources: [{ title: 'Источник', unknown: 'поле' }] },
        { unknown: true }
    ];

    for (const change of invalid) {
        const content = { ...ownText().content, ...change };
        assert.throws(() => readBookTextContent(content), TypeError);
    }
});

test('Перемещение главы сохраняет соседний собственный текст', () => {
    const source = toc();
    source.push(ownText('root-text', null, 1));

    const result = applyChapterCommand(source, { type: 'move', key: 'main', delta: 1 });

    assert.equal(result.find((node) => node.key === 'main').position, 1);
    assert.equal(result.find((node) => node.key === 'root-text').position, 0);
    assert.deepEqual(result[1].content, source[1].content);
});

test('Главу с собственным текстом нельзя удалить как пустую', () => {
    const source = toc().slice(0, 2);

    assert.throws(() => applyChapterCommand(source, { type: 'remove', key: 'main' }), TypeError);
});

test('Прежнее добавление внешнего материала работает рядом с собственным текстом', () => {
    const source = toc();
    const publication = {
        id: VERSION,
        article_id: ARTICLE,
        version_number: 1,
        content_json: { schema_version: 1, title: 'Материал', body: 'Текст публикации.', sources: [] }
    };
    const command = { type: 'attach', key: 'another-external', parent_key: 'main', publication };
    const result = applySectionCommand(source, command);

    assert.deepEqual(result[1], source[1]);
    assert.equal(result.at(-1).article_version_id, VERSION);
    assert.equal(result.at(-1).position, 2);
});

test('Неизвестная команда отклоняется без изменения исходных данных', () => {
    const source = toc();
    const before = structuredClone(source);

    assert.throws(() => applyBookTextCommand(source, { type: 'replace', key: 'checks' }), TypeError);
    assert.deepEqual(source, before);
});
