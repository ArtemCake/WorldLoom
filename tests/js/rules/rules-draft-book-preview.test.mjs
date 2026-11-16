// tests/js/rules/rules-draft-book-preview.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { createArticlesApi } from '../../../frontend/src/js/features/rules/articles-api.js';
import { buildDraftBookPreview, readDraftPreviewInput } from '../../../frontend/src/js/features/rules/draft/draft-book-preview-data.js';
import { draftPreviewVersionIds } from '../../../frontend/src/js/features/rules/draft/draft-book-preview-data.js';
import { createDraftBookPreview } from '../../../frontend/src/js/features/rules/draft/draft-book-preview-state.js';

function localContent(title = 'Локальный раздел') {
    return {
        schema_version: 1,
        title,
        summary: '',
        body: '**Несохранённый текст**',
        language: 'ru',
        edition_key: null,
        audience: 'both',
        rule_kind: 'base',
        sources: [{ title: 'Источник собственного текста' }]
    };
}

function publication(title = 'Внешний раздел') {
    return {
        id: randomUUID(),
        article_id: randomUUID(),
        version_number: 2,
        content_json: { ...localContent(title), body: 'Точная закреплённая публикация' }
    };
}

function editorState(version = null) {
    const toc = [
        {
            kind: 'text',
            key: 'local',
            parent_key: 'chapter',
            position: 20,
            title: null,
            content: localContent()
        },
        {
            kind: 'chapter',
            key: 'chapter',
            parent_key: null,
            position: 0,
            title: 'Глава'
        }
    ];

    if (version) {
        toc.push({
            kind: 'article',
            key: 'external',
            parent_key: 'chapter',
            position: 10,
            title: 'Название в оглавлении',
            article_version_id: version.id
        });
    }

    return {
        schemaVersion: 2,
        values: { title: 'Локальная книга', introduction: 'Несохранённое введение' },
        sources: [{ title: 'Общий источник книги' }],
        toc
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

test('API запрашивает точную публикацию и передаёт сигнал отмены', async () => {
    const id = randomUUID();
    const signal = new AbortController().signal;
    const calls = [];
    const api = createArticlesApi(async (...args) => {
        calls.push(args);
        return { id };
    });

    assert.deepEqual(await api.getVersionById(id, { signal }), { id });
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], `/rules/articles/versions/${id}`);
    assert.equal(calls[0][1].signal, signal);
    assert.throws(() => api.getVersionById('invalid'), TypeError);
});

test('Сборка сортирует пункты, сохраняет локальные тексты и оба вида источников', () => {
    const external = publication();
    const state = editorState(external);
    const before = structuredClone(state);
    const book = buildDraftBookPreview(readDraftPreviewInput(state), [external]);

    assert.deepEqual(book.sections.map((node) => node.key), ['chapter', 'external', 'local']);
    assert.deepEqual(book.sections.map((node) => node.depth), [0, 1, 1]);
    assert.equal(book.sections[1].title, 'Название в оглавлении');
    assert.equal(book.sections[1].body, external.content_json.body);
    assert.equal(book.sections[2].body, '**Несохранённый текст**');
    assert.equal(book.sections[2].sources[0].title, 'Источник собственного текста');
    assert.equal(book.sources[0].title, 'Общий источник книги');
    assert.equal(book.introduction, 'Несохранённое введение');
    assert.equal(book.version, null);
    assert.deepEqual(state, before);
});

test('Повторное использование публикации не требует повторной загрузки', () => {
    const external = publication();
    const state = editorState(external);
    state.toc.push({
        kind: 'article',
        key: 'external-again',
        parent_key: null,
        position: 1,
        title: null,
        article_version_id: external.id
    });

    const input = readDraftPreviewInput(state);
    const book = buildDraftBookPreview(input, [external]);

    assert.deepEqual(draftPreviewVersionIds(input), [external.id]);
    assert.equal(book.sections.at(-1).title, external.content_json.title);
    assert.equal(book.sections.filter((node) => node.body === external.content_json.body).length, 2);
});

test('Отсутствующая, посторонняя и повторная публикации отклоняются', () => {
    const external = publication();
    const input = readDraftPreviewInput(editorState(external));

    assert.throws(() => buildDraftBookPreview(input, []), TypeError);
    assert.throws(() => buildDraftBookPreview(input, [publication()]), TypeError);
    assert.throws(() => buildDraftBookPreview(input, [external, external]), TypeError);
});

test('Рабочий формат допускает пустой текст, прежний формат не принимает собственные тексты', () => {
    const state = editorState();
    state.toc[0].content.body = '';

    assert.equal(buildDraftBookPreview(readDraftPreviewInput(state), []).sections[1].body, '');

    state.schemaVersion = 1;
    assert.throws(() => readDraftPreviewInput(state), TypeError);
});

test('Снимок предпросмотра не меняется вслед за редактором', () => {
    const state = editorState();
    const input = readDraftPreviewInput(state);
    state.values.title = 'Новое название';
    state.toc[0].content.body = 'Новый текст';

    const book = buildDraftBookPreview(input, []);

    assert.equal(book.title, 'Локальная книга');
    assert.equal(book.sections[1].body, '**Несохранённый текст**');
});

test('Книга без внешних разделов собирается без сетевых запросов', async () => {
    let calls = 0;
    const preview = createDraftBookPreview({
        loadVersion: async () => {
            calls += 1;
            throw new Error('Запрос не должен выполняться');
        }
    });

    await preview.open(editorState());

    assert.equal(calls, 0);
    assert.equal(preview.getState().loading, false);
    assert.equal(preview.getState().book.title, 'Локальная книга');
    preview.dispose();
});

test('Ошибка загрузки не оставляет частичный или предыдущий предпросмотр', async () => {
    const external = publication();
    const preview = createDraftBookPreview({
        loadVersion: async () => { throw Object.assign(new Error('Недоступно'), { status: 404 }); }
    });

    await preview.open(editorState());
    assert.ok(preview.getState().book);

    await preview.open(editorState(external));

    assert.equal(preview.getState().book, null);
    assert.equal(preview.getState().loading, false);
    assert.ok(preview.getState().error.includes('недоступна'));
    preview.dispose();
});

test('Ответ с другой публикацией не принимается', async () => {
    const external = publication();
    const preview = createDraftBookPreview({ loadVersion: async () => publication('Другая версия') });

    await preview.open(editorState(external));

    assert.equal(preview.getState().book, null);
    assert.ok(preview.getState().error);
    preview.dispose();
});

test('Новое открытие отменяет старое и не принимает его запоздалый ответ', async () => {
    const external = publication();
    const pending = deferred();
    let signal;
    const preview = createDraftBookPreview({
        loadVersion: (id, options) => {
            assert.equal(id, external.id);
            signal = options.signal;
            return pending.promise;
        }
    });

    const first = preview.open(editorState(external));
    const next = editorState();
    next.values.title = 'Следующая книга';

    await preview.open(next);
    assert.equal(signal.aborted, true);

    pending.resolve(external);
    await first;

    assert.equal(preview.getState().book.title, 'Следующая книга');
    preview.dispose();
});

test('Закрытие отменяет загрузку и оставляет предпросмотр закрытым', async () => {
    const external = publication();
    const pending = deferred();
    let signal;
    const preview = createDraftBookPreview({
        loadVersion: (id, options) => {
            signal = options.signal;
            return pending.promise;
        }
    });

    const opening = preview.open(editorState(external));
    preview.close();
    pending.resolve(external);
    await opening;

    assert.equal(signal.aborted, true);
    assert.deepEqual(preview.getState(), { opened: false, loading: false, error: '', book: null });
    preview.dispose();
});

test('Одновременно выполняется не больше четырёх запросов, каждая версия читается один раз', async () => {
    const versions = Array.from({ length: 9 }, () => publication());
    const state = editorState();
    const seen = [];
    let active = 0;
    let maximum = 0;
    const preview = createDraftBookPreview({
        loadVersion: async (id) => {
            seen.push(id);
            active += 1;
            maximum = Math.max(maximum, active);
            await new Promise((resolve) => setTimeout(resolve, 0));
            active -= 1;
            return versions.find((version) => version.id === id);
        }
    });

    versions.forEach((version, index) => {
        state.toc.push({
            kind: 'article',
            key: `external-${index}`,
            parent_key: null,
            position: index + 1,
            title: null,
            article_version_id: version.id
        });
    });

    await preview.open(state);

    assert.equal(maximum, 4);
    assert.equal(seen.length, versions.length);
    assert.equal(new Set(seen).size, versions.length);
    assert.equal(preview.getState().error, '');
    assert.equal(preview.getState().book.sections.length, 11);
    preview.dispose();
});

test('Уничтоженный контроллер не публикует результат незавершённой загрузки', async () => {
    const external = publication();
    const pending = deferred();
    const changes = [];
    const preview = createDraftBookPreview({
        loadVersion: () => pending.promise,
        onChange: (state) => changes.push(state)
    });

    const opening = preview.open(editorState(external));
    preview.dispose();
    const count = changes.length;

    pending.resolve(external);
    await opening;
    await preview.open(editorState());

    assert.equal(changes.length, count);
    assert.equal(preview.getState().book, null);
});
