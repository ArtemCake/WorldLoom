// frontend/src/js/features/rules/authoring/authoring-navigation.js

export function createAuthoringNavigation({ root, getState, notify }) {
    const document = root.ownerDocument;
    const window = document.defaultView;
    const events = new AbortController();
    const options = { signal: events.signal };
    const acceptedLinks = new WeakSet();

    function allow() {
        const state = getState();

        if (!state?.needsGuard) return true;

        if (state.busy) {
            notify('Дождитесь ответа на текущий запрос, прежде чем менять открытую книгу.');
            return false;
        }

        const message = state.blocked
            ? 'Есть локальный текст и неразрешённый результат записи. Продолжить без сохранения локальной формы?'
            : 'В форме есть несохранённые изменения. Продолжить без их сохранения?';

        return window.confirm(message);
    }

    function beforeUnload(event) {
        if (!getState()?.needsGuard) return;
        event.preventDefault();
        event.returnValue = '';
    }

    function onClick(event) {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;

        const link = event.target.closest?.('a[href]');
        if (!link || link.hasAttribute('download')) return;
        if (link.target && link.target !== '_self') return;

        const destination = new URL(link.href, window.location.href);
        const current = new URL(window.location.href);
        const sameDocument = destination.origin === current.origin && destination.pathname === current.pathname;
        const sameQuery = destination.search === current.search;

        if (sameDocument && sameQuery && destination.hash) return;

        if (!allow()) {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
        }

        acceptedLinks.add(link);
        window.setTimeout(() => acceptedLinks.delete(link), 0);
    }

    function beforeRequest(event) {
        const target = event.detail?.target;
        const replacesWorkspace = target && (target === root || target.contains?.(root) || root.contains(target));

        if (!replacesWorkspace) return;

        const link = event.detail?.elt?.closest?.('a[href]');

        if (link && acceptedLinks.has(link)) {
            acceptedLinks.delete(link);
            return;
        }

        if (!allow()) event.preventDefault();
    }

    window.addEventListener('beforeunload', beforeUnload, options);
    document.addEventListener('click', onClick, { ...options, capture: true });
    document.addEventListener('htmx:beforeRequest', beforeRequest, options);

    return Object.freeze({ allow, dispose: () => events.abort() });
}
