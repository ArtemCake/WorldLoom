// tests/js/rules/rules-authoring-navigation.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createAuthoringNavigation } from '../../../frontend/src/js/features/rules/authoring/authoring-navigation.js';

function setup(state, answer = false) {
    const window = new EventTarget();
    const document = new EventTarget();
    const notices = [];
    let confirmations = 0;

    window.confirm = () => {
        confirmations += 1;
        return answer;
    };

    document.defaultView = window;
    const root = { ownerDocument: document, contains: () => false };
    const guard = createAuthoringNavigation({
        root,
        getState: () => state,
        notify: (message) => notices.push(message)
    });

    return { guard, window, notices, confirmations: () => confirmations };
}

test('Чистая форма не требует подтверждения', () => {
    const { guard, confirmations } = setup({ needsGuard: false });

    assert.equal(guard.allow(), true);
    assert.equal(confirmations(), 0);
    guard.dispose();
});

test('Отказ от выхода оставляет форму открытой', () => {
    const { guard, confirmations } = setup({ needsGuard: true, busy: '', blocked: false });

    assert.equal(guard.allow(), false);
    assert.equal(confirmations(), 1);
    guard.dispose();
});

test('Во время записи внутренний переход блокируется без предложения потерять результат', () => {
    const { guard, notices, confirmations } = setup({ needsGuard: true, busy: 'save' });

    assert.equal(guard.allow(), false);
    assert.equal(confirmations(), 0);
    assert.equal(notices.length, 1);
    guard.dispose();
});

test('Закрытие вкладки предупреждает о несохранённом состоянии', () => {
    const { guard, window } = setup({ needsGuard: true });
    const event = new Event('beforeunload', { cancelable: true });

    window.dispatchEvent(event);

    assert.equal(event.defaultPrevented, true);
    guard.dispose();
});

test('После уничтожения предупреждение не остаётся висеть на странице', () => {
    const { guard, window } = setup({ needsGuard: true });
    guard.dispose();

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);

    assert.equal(event.defaultPrevented, false);
});
