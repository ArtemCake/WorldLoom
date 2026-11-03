// frontend/src/js/features/games/sessions/session-token-events.js

const EVENT_NAME = 'worldloom:session-tokens-changed';
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function readSessionId(root) {
    if (!(root instanceof Element)) return null;

    const sessionId = root.dataset.sessionId;

    return typeof sessionId === 'string' && UUID_PATTERN.test(sessionId) ? sessionId : null;
}

export function notifySessionTokensChanged(root) {
    const sessionId = readSessionId(root);

    if (!sessionId) return;

    document.dispatchEvent(new CustomEvent(EVENT_NAME, {
        detail: { sessionId, source: root }
    }));
}

export function subscribeSessionTokensChanged(root, callback, signal) {
    const sessionId = readSessionId(root);

    if (!sessionId) {
        throw new Error('Для связи компонентов токенов необходимо указать корректную сессию.');
    }

    document.addEventListener(EVENT_NAME, (event) => {
        const detail = event.detail;

        if (!root.isConnected || !detail || detail.sessionId !== sessionId || detail.source === root) return;

        callback();
    }, { signal });
}