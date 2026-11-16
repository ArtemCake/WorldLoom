// tests/js/rules/rules-draft-preview-session.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { createDraftPreviewSession } from '../../../frontend/src/js/features/rules/draft/draft-book-preview-session.js';

function editorState() {
    return {
        schemaVersion: 2,
        values: {
            title: 'Книга',
            summary: '',
            introduction: 'Первое введение',
            language: 'ru',
            edition_key: null
        },
        sources: [],
        toc: [],
        busy: false,
        blocked: false,
        dirty: false,
        revision: 1
    };
}

function session(options = {}) {
    return createDraftPreviewSession({
        loadVersion: async () => { throw new Error('Загрузка не ожидается'); },
        ...options
    });
}

function externalPublication() {
    return {
        id: randomUUID(),
        article_id: randomUUID(),
        version_number: 1,
        content_json: {
            schema_version: 1,
            title: 'Внешний раздел',
            summary: '',
            body: 'Закреплённый текст',
            language: 'ru',
            edition_key: null,
            audience: 'both',
            rule_kind: 'base',
            sources: []
        }
    };
}

test('Без редактора предпросмотр недоступен, после обновления открывает локальную книгу', async () => {
    const preview = session();

    assert.equal(preview.getState().available, false);
    await preview.open();
    assert.equal(preview.getState().opened, false);

    preview.update(editorState());
    await preview.open();

    assert.equal(preview.getState().available, true);
    assert.equal(preview.getState().book.title, 'Книга');
    assert.equal(preview.getState().stale, false);
    preview.dispose();
});

test('Изменение содержания отмечает снимок устаревшим, но не заменяет прочитанный текст', async () => {
    const preview = session();
    const state = editorState();

    preview.update(state);
    await preview.open();

    const generation = preview.getState().generation;
    state.values.introduction = 'Новое введение';
    preview.update(state);

    assert.equal(preview.getState().stale, true);
    assert.equal(preview.getState().book.introduction, 'Первое введение');
    assert.equal(preview.getState().generation, generation);

    state.values.introduction = 'Первое введение';
    preview.update(state);

    assert.equal(preview.getState().stale, false);
    preview.dispose();
});

test('Изменение ревизии и служебных состояний не делает неизменное содержание устаревшим', async () => {
    const preview = session();
    const state = editorState();

    preview.update(state);
    await preview.open();

    state.revision = 2;
    state.dirty = true;
    state.blocked = true;
    state.busy = 'save';
    preview.update(state);

    assert.equal(preview.getState().stale, false);
    assert.equal(preview.getState().busy, true);

    state.busy = false;
    preview.update(state);

    assert.equal(preview.getState().busy, false);
    assert.equal(preview.getState().stale, false);
    preview.dispose();
});

test('Повторная сборка принимает новое содержание и снимает отметку устаревания', async () => {
    const preview = session();
    const state = editorState();

    preview.update(state);
    await preview.open();
    const generation = preview.getState().generation;

    state.values.title = 'Новое название';
    preview.update(state);
    await preview.open();

    assert.equal(preview.getState().book.title, 'Новое название');
    assert.equal(preview.getState().generation, generation + 1);
    assert.equal(preview.getState().stale, false);
    preview.dispose();
});

test('Закрытие сохраняет доступность кнопки, сброс удаляет привязку к редактору', async () => {
    const preview = session();

    preview.update(editorState());
    await preview.open();
    preview.close();

    assert.equal(preview.getState().opened, false);
    assert.equal(preview.getState().available, true);
    assert.equal(preview.getState().book, null);

    await preview.open();
    assert.ok(preview.getState().book);

    preview.reset();

    assert.equal(preview.getState().available, false);
    assert.equal(preview.getState().opened, false);
    assert.equal(preview.getState().book, null);
    preview.dispose();
});

test('Во время операции редактора новая сборка не начинается, при конфликте локальный просмотр разрешён', async () => {
    const preview = session();
    const state = editorState();
    state.busy = 'save';

    preview.update(state);
    await preview.open();

    assert.equal(preview.getState().opened, false);

    state.busy = false;
    state.blocked = true;
    preview.update(state);
    await preview.open();

    assert.equal(preview.getState().book.title, 'Книга');
    assert.equal(state.blocked, true);
    preview.dispose();
});

test('Изменение во время загрузки сохраняет исходный снимок и отмечает его устаревшим', async () => {
    const external = externalPublication();
    let resolve;
    const pending = new Promise((done) => { resolve = done; });
    const preview = session({ loadVersion: () => pending });
    const state = editorState();

    state.toc.push({
        kind: 'article',
        key: 'external',
        parent_key: null,
        position: 0,
        title: null,
        article_version_id: external.id
    });

    preview.update(state);
    const opening = preview.open();

    state.values.title = 'Изменено при загрузке';
    preview.update(state);

    resolve(external);
    await opening;

    assert.equal(preview.getState().book.title, 'Книга');
    assert.equal(preview.getState().stale, true);
    preview.dispose();
});

test('Сброс отменяет загрузку и не допускает появления старой книги', async () => {
    const external = externalPublication();
    let resolve;
    let signal;
    const pending = new Promise((done) => { resolve = done; });
    const preview = session({
        loadVersion: (id, options) => {
            assert.equal(id, external.id);
            signal = options.signal;
            return pending;
        }
    });
    const state = editorState();

    state.toc.push({
        kind: 'article',
        key: 'external',
        parent_key: null,
        position: 0,
        title: null,
        article_version_id: external.id
    });

    preview.update(state);
    const opening = preview.open();

    preview.reset();
    assert.equal(signal.aborted, true);

    resolve(external);
    await opening;

    assert.equal(preview.getState().opened, false);
    assert.equal(preview.getState().book, null);
    assert.equal(preview.getState().available, false);
    preview.dispose();
});

test('После уничтожения обновления не вызывают уведомлений и загрузки', async () => {
    const changes = [];
    const preview = session({ onChange: (state) => changes.push(state) });

    preview.update(editorState());
    preview.dispose();
    const count = changes.length;

    preview.update(editorState());
    await preview.open();
    preview.close();
    preview.reset();

    assert.equal(changes.length, count);
    assert.equal(preview.getState().available, false);
});
