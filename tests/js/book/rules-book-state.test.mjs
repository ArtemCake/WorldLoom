import test from 'node:test';
import assert from 'node:assert/strict';

import {BOOK_CHAPTERS, createRulesBookState} from '../../../frontend/src/js/features/game-systems/book/book-state.js';

function document() {
    return {
        system: {
            name: 'Пограничье',
            slug: 'borderlands',
            description: 'Правила приключений',
            is_active: true,
            rules_engine_version: '1.0'
        },
        rules: {
            schema_version: 4,
            calculations: {
                attributes: {
                    endurance: {label: 'Выносливость', min_value: 1, max_value: 20}
                },
                derived: {}
            },
            initial_attributes: {endurance: 10},
            resources: {
                stamina: {
                    label: 'Запас сил',
                    maximum: 'attribute.endurance',
                    initial: 'full',
                    recovery: {rest: 'full'}
                }
            }
        },
        origin: null
    };
}

function editable() {
    return createRulesBookState({document: document(), mode: 'edit', revision: 3});
}

test('все главы доступны, переключение не изменяет документ', () => {
    const state = editable();

    for (const chapter of BOOK_CHAPTERS) {
        state.selectChapter(chapter.code);
        assert.equal(state.read().chapter, chapter.code);
    }

    assert.equal(state.read().dirty, false);
});

test('старые настройки и сведения об основе не теряются при загрузке', () => {
    const source = document();

    source.rules = {
        schema_version: 2,
        attribute_mode: 'score',
        max_level: 20,
        modifier_offset: 10,
        modifier_divisor: 2,
        modifier_formula: null,
        calculations: {
            attributes: {
                strength: {label: 'Сила', min_value: 1, max_value: 30, modifier_formula: null}
            },
            derived: {}
        }
    };

    source.origin = {publication: {version_number: 2}, overrides: {calculations: source.rules.calculations}};

    const state = createRulesBookState({document: source, revision: 3});

    assert.deepEqual(state.read().document, source);

    source.rules.modifier_offset = 12;

    assert.equal(state.read().document.rules.modifier_offset, 10);
});

test('полученный снимок не позволяет изменить внутреннее состояние', () => {
    const state = editable();
    const snapshot = state.read();

    snapshot.document.rules.resources.stamina.recovery.rest = 2;

    assert.equal(state.read().document.rules.resources.stamina.recovery.rest, 'full');
    assert.equal(state.read().dirty, false);
});

test('ошибка изменения не оставляет частично изменённый документ', () => {
    const state = editable();
    const before = state.read();

    assert.throws(() => state.update((draft) => {
        draft.system.name = 'Другое название';
        throw new Error('Изменение отменено');
    }), /отменено/);

    assert.deepEqual(state.read(), before);
});

test('неподдерживаемые значения не удаляются из документа молча', () => {
    const state = editable();

    assert.throws(() => state.update((draft) => {
        draft.system.description = undefined;
    }), /JSON/);

    assert.equal(state.read().document.system.description, 'Правила приключений');
    assert.equal(state.read().dirty, false);
});

test('возврат исходного значения снимает признак изменения', () => {
    const state = editable();

    state.update((draft) => { draft.system.name = 'Новый мир'; });
    assert.equal(state.read().dirty, true);

    state.update((draft) => { draft.system.name = 'Пограничье'; });
    assert.equal(state.read().dirty, false);
});

test('просмотр запрещает правки и запись, но разрешает проверку примера', () => {
    const state = createRulesBookState({document: document(), mode: 'view', revision: 3});

    assert.throws(() => state.update(() => {}), /просмотра/);
    assert.throws(() => state.beginSave(), /просмотра/);
    assert.throws(() => state.beginPublish(), /просмотра/);

    state.setSample({attributes: {endurance: 12}});

    const ticket = state.beginPreview();
    const result = {attributes: {endurance: 12}, resource_limits: {stamina: 12}};

    assert.equal(state.acceptPreview(ticket, result), true);
    assert.deepEqual(state.read().preview, result);
    assert.equal(state.read().dirty, false);
});

test('результат для старой версии правил не принимается', () => {
    const state = editable();
    const ticket = state.beginPreview();

    state.update((draft) => { draft.rules.initial_attributes.endurance = 12; });

    assert.equal(state.acceptPreview(ticket, {derived: {}}), false);
    assert.equal(state.read().preview, null);
});

test('изменение примера отменяет ожидаемый результат, но не меняет правила', () => {
    const state = editable();
    const ticket = state.beginPreview();

    state.setSample({attributes: {endurance: 15}});

    assert.equal(state.acceptPreview(ticket, {derived: {}}), false);
    assert.equal(state.read().dirty, false);
    assert.equal(Object.hasOwn(state.read().document, 'sample'), false);
});

test('сохранение блокирует повторную запись и принимает новую ревизию', () => {
    const state = editable();

    state.update((draft) => { draft.system.name = 'Новый мир'; });

    const ticket = state.beginSave();

    assert.equal(ticket.expectedRevision, 3);
    assert.throws(() => state.beginSave(), /текущей записи/);
    assert.throws(() => state.update(() => {}), /текущей записи/);

    state.acceptSave(ticket, ticket.document, 4);

    assert.equal(state.read().revision, 4);
    assert.equal(state.read().dirty, false);
    assert.equal(state.read().writePending, null);
});

test('ответ другой книги нельзя принять за результат своей записи', () => {
    const first = editable();
    const second = editable();
    const firstTicket = first.beginSave();
    const secondTicket = second.beginSave();

    assert.throws(() => first.acceptSave(secondTicket, secondTicket.document, 4), /текущей операции/);
    assert.equal(first.read().writePending, 'save');

    first.acceptSave(firstTicket, firstTicket.document, 4);
});

test('прежняя ревизия не считается успешным сохранением', () => {
    const state = editable();
    const ticket = state.beginSave();

    assert.throws(() => state.acceptSave(ticket, ticket.document, 3), /новой ревизии/);
    assert.equal(state.read().writePending, 'save');
});

test('неопределённый результат блокирует запись, не уничтожая изменения', () => {
    const state = editable();

    state.update((draft) => { draft.system.name = 'Новый мир'; });

    const ticket = state.beginSave();

    state.failWrite(ticket, {mustReload: true});

    assert.equal(state.read().blocked, true);
    assert.equal(state.read().dirty, true);
    assert.equal(state.read().document.system.name, 'Новый мир');
    assert.throws(() => state.beginSave(), /сверьте/);
});

test('подтверждённый отказ без записи допускает исправление и повтор', () => {
    const state = editable();
    const ticket = state.beginSave();

    state.failWrite(ticket);

    assert.equal(state.read().blocked, false);
    assert.doesNotThrow(() => state.beginSave());
});

test('публиковать можно только сохранённый черновик', () => {
    const state = editable();

    state.update((draft) => { draft.system.description = 'Новая редакция'; });

    assert.throws(() => state.beginPublish(), /сохраните/);

    const save = state.beginSave();

    state.acceptSave(save, save.document, 4);

    const publication = state.beginPublish();

    assert.equal(publication.expectedRevision, 4);
    assert.throws(() => state.beginPublish(), /текущей записи/);

    state.acceptPublish(publication);

    assert.equal(state.read().dirty, false);
});

test('новая книга становится редактируемой после подтверждённого сохранения', () => {
    const state = createRulesBookState({document: document(), mode: 'create'});

    assert.equal(state.read().dirty, true);
    assert.equal(state.read().canPublish, false);

    const ticket = state.beginSave();

    assert.equal(ticket.expectedRevision, null);

    state.acceptSave(ticket, ticket.document, 1);

    assert.equal(state.read().mode, 'edit');
    assert.equal(state.read().dirty, false);
    assert.equal(state.read().canPublish, true);
});
