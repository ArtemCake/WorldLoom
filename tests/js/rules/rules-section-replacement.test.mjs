// tests/js/rules/rules-section-replacement.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { applySectionReplacement } from '../../../frontend/src/js/features/rules/draft/draft-section-replacement-data.js';
import { createSectionReplacement } from '../../../frontend/src/js/features/rules/draft/draft-section-replacement-state.js';
import { createBookDraftEditor } from '../../../frontend/src/js/features/rules/draft/draft-editor-state.js';

const ARTICLE = '11111111-1111-4111-8111-111111111111';
const OLD = '22222222-2222-4222-8222-222222222222';
const NEXT = '33333333-3333-4333-8333-333333333333';
const OTHER = '44444444-4444-4444-8444-444444444444';

function publication(id = NEXT, number = 2, articleId = ARTICLE) {
    return {
        id,
        article_id: articleId,
        version_number: number,
        content_json: {
            schema_version: 1,
            title: `Название версии ${number}`,
            body: `Текст версии ${number}`,
            sources: [{ title: `Источник версии ${number}` }]
        }
    };
}

function node(key = 'checks', position = 0) {
    return {
        kind: 'article',
        key,
        parent_key: null,
        position,
        title: 'Название внутри книги',
        article_version_id: OLD
    };
}

function command() {
    return {
        type: 'replace',
        key: 'checks',
        expected_version_id: OLD,
        current: publication(OLD, 1),
        publication: publication()
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

test('Замена меняет только ссылку выбранного вхождения', () => {
    const source = [node(), node('second', 1)];
    const result = applySectionReplacement(source, command());

    assert.deepEqual(result[0], { ...source[0], article_version_id: NEXT });
    assert.deepEqual(result[1], source[1]);
    assert.equal(source[0].article_version_id, OLD);
    assert.equal(result[0].title, 'Название внутри книги');
    assert.equal(Object.hasOwn(result[0], 'body'), false);
    assert.equal(Object.hasOwn(result[0], 'sources'), false);
});

test('Родительская глава и позиция сохраняются', () => {
    const chapter = { kind: 'chapter', key: 'main', parent_key: null, position: 0, title: 'Глава' };
    const section = { ...node(), parent_key: 'main', position: 7 };
    const result = applySectionReplacement([chapter, section], command());

    assert.equal(result[1].parent_key, 'main');
    assert.equal(result[1].position, 7);
    assert.equal(result[1].key, section.key);
});

test('Отсутствие собственного названия сохраняется', () => {
    const result = applySectionReplacement([{ ...node(), title: null }], command());

    assert.equal(result[0].title, null);
});

test('Устаревшее сравнение не заменяет уже изменённую ссылку', () => {
    const source = [{ ...node(), article_version_id: OTHER }];

    assert.throws(() => applySectionReplacement(source, command()), /уже изменилась/u);
    assert.equal(source[0].article_version_id, OTHER);
});

test('Нельзя заменить публикацией другой статьи', () => {
    const request = command();
    request.publication.article_id = OTHER;

    assert.throws(() => applySectionReplacement([node()], request), TypeError);
});

test('Повтор уже закреплённой публикации отклоняется', () => {
    const request = command();
    request.publication = publication(OLD, 1);

    assert.throws(() => applySectionReplacement([node()], request), /уже закреплена/u);
});

test('Удалённый пункт не создаётся заново при применении сравнения', () => {
    assert.throws(() => applySectionReplacement([], command()), /не найден/u);
});

test('Сравнение проверяет старую публикацию через статью нового материала', async () => {
    const calls = [];
    const state = createSectionReplacement({
        api: {
            getVersion: async (...args) => {
                calls.push(args);
                return publication(OLD, 1);
            }
        }
    });

    await state.compare({ node: node(), publication: publication() });

    assert.equal(calls[0][0], ARTICLE);
    assert.equal(calls[0][1], OLD);
    assert.ok(calls[0][2].signal instanceof AbortSignal);
    assert.equal(state.getState().canApply, true);
    assert.deepEqual(state.getCommand(), command());
});

test('До завершения чтения применение недоступно', async () => {
    const pending = deferred();
    const state = createSectionReplacement({ api: { getVersion: async () => pending.promise } });
    const loading = state.compare({ node: node(), publication: publication() });

    assert.equal(state.getState().reading, true);
    assert.equal(state.getState().canApply, false);
    assert.throws(() => state.getCommand(), TypeError);

    pending.resolve(publication(OLD, 1));
    await loading;

    assert.equal(state.getState().canApply, true);
});

test('Подмена старой публикации не подтверждает сравнение', async () => {
    const state = createSectionReplacement({
        api: { getVersion: async () => publication(OTHER, 1) }
    });

    await state.compare({ node: node(), publication: publication() });

    assert.equal(state.getState().current, null);
    assert.equal(state.getState().canApply, false);
    assert.ok(state.getState().error);
});

test('Ошибка чтения не оставляет применимым прежнее сравнение', async () => {
    let fail = false;
    const state = createSectionReplacement({
        api: {
            getVersion: async () => {
                if (fail) throw new Error('Публикация недоступна');
                return publication(OLD, 1);
            }
        }
    });

    await state.compare({ node: node(), publication: publication() });
    assert.equal(state.getState().canApply, true);

    fail = true;
    await state.compare({ node: node(), publication: publication() });

    assert.equal(state.getState().canApply, false);
    assert.equal(state.getState().current, null);
    assert.match(state.getState().error, /недоступна/u);
});

test('Запоздалое сравнение не заменяет более новое', async () => {
    const first = deferred();
    let calls = 0;
    const state = createSectionReplacement({
        api: {
            getVersion: async () => {
                calls += 1;
                return calls === 1 ? first.promise : publication(OLD, 1);
            }
        }
    });

    const oldRequest = state.compare({ node: node(), publication: publication() });
    await state.compare({ node: node('second', 1), publication: publication(OTHER, 3) });

    first.resolve(publication(OLD, 1));
    await oldRequest;

    assert.equal(state.getState().node.key, 'second');
    assert.equal(state.getCommand().publication.id, OTHER);
});

test('Закрытие отменяет запрос и игнорирует его поздний результат', async () => {
    const pending = deferred();
    let signal;
    const state = createSectionReplacement({
        api: {
            getVersion: async (_article, _version, options) => {
                signal = options.signal;
                return pending.promise;
            }
        }
    });

    const loading = state.compare({ node: node(), publication: publication() });
    state.close();

    assert.equal(signal.aborted, true);
    pending.resolve(publication(OLD, 1));
    await loading;

    assert.equal(state.getState().opened, false);
    assert.equal(state.getState().canApply, false);
    assert.throws(() => state.getCommand(), TypeError);
});

test('Возвращаемые данные не позволяют изменить внутреннюю команду', async () => {
    const state = createSectionReplacement({
        api: { getVersion: async () => publication(OLD, 1) }
    });

    await state.compare({ node: node(), publication: publication() });

    const snapshot = state.getState();
    const request = state.getCommand();
    snapshot.current.article_id = OTHER;
    request.publication.id = OTHER;

    assert.equal(state.getCommand().current.article_id, ARTICLE);
    assert.equal(state.getCommand().publication.id, NEXT);
});

test('Уничтоженное состояние не обновляет интерфейс после завершения запроса', async () => {
    const pending = deferred();
    const snapshots = [];
    const state = createSectionReplacement({
        api: { getVersion: async () => pending.promise },
        onChange: (value) => snapshots.push(value)
    });

    const loading = state.compare({ node: node(), publication: publication() });
    state.dispose();
    const count = snapshots.length;

    pending.resolve(publication(OLD, 1));
    await loading;

    assert.equal(snapshots.length, count);
    assert.equal(state.getState().canApply, false);
});

test('Замена сохраняется вместе с формой, не меняя прочее содержание книги', async () => {
    const source = {
        id: OTHER,
        book_id: ARTICLE,
        revision: 5,
        content_json: {
            schema_version: 1,
            title: 'Книга',
            summary: '',
            introduction: 'Введение',
            language: 'ru',
            edition_key: null,
            category: 'rules',
            audience: 'gm',
            sources: [{ title: 'Источник книги' }],
            toc: [node(), node('second', 1)]
        }
    };
    const calls = [];
    const editor = createBookDraftEditor({
        draft: source,
        api: {
            getDraft: async () => structuredClone(source),
            saveDraft: async (bookId, payload) => {
                calls.push({ bookId, payload: structuredClone(payload) });
                return { ...source, revision: 6, content_json: structuredClone(payload.content) };
            }
        }
    });

    editor.change('title', 'Обновлённая книга');
    assert.equal(editor.section(command()), true);
    assert.equal(editor.getState().dirty, true);
    assert.equal(editor.getState().needsGuard, true);

    await editor.save();

    assert.equal(calls.length, 1);
    assert.equal(calls[0].payload.expected_revision, 5);
    assert.equal(calls[0].payload.content.title, 'Обновлённая книга');
    assert.equal(calls[0].payload.content.toc[0].article_version_id, NEXT);
    assert.deepEqual(calls[0].payload.content.toc[1], source.content_json.toc[1]);
    assert.deepEqual(calls[0].payload.content.sources, source.content_json.sources);
    assert.equal(calls[0].payload.content.introduction, 'Введение');
    assert.equal(calls[0].payload.content.category, 'rules');
    assert.equal(calls[0].payload.content.audience, 'gm');
    assert.equal(source.content_json.toc[0].article_version_id, OLD);
    assert.equal(editor.getState().dirty, false);
});

test('Неудачная замена не меняет локальное оглавление редактора', () => {
    const source = {
        id: OTHER,
        book_id: ARTICLE,
        revision: 1,
        content_json: {
            schema_version: 1,
            title: 'Книга',
            summary: '',
            introduction: '',
            language: 'ru',
            edition_key: null,
            category: 'rules',
            audience: 'gm',
            sources: [],
            toc: [node()]
        }
    };
    const editor = createBookDraftEditor({
        draft: source,
        api: {
            getDraft: async () => structuredClone(source),
            saveDraft: async () => assert.fail('Сохранение не ожидается')
        }
    });
    const request = command();
    request.expected_version_id = OTHER;

    assert.throws(() => editor.section(request), TypeError);
    assert.deepEqual(editor.getState().toc, source.content_json.toc);
    assert.equal(editor.getState().dirty, false);
});
