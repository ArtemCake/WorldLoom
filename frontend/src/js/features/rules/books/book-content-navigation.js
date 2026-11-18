// frontend/src/js/features/rules/books/book-content-navigation.js

function ordinaryActivation(event) {
    return !event.defaultPrevented
        && event.button === 0
        && !event.ctrlKey
        && !event.metaKey
        && !event.shiftKey
        && !event.altKey;
}

export function createBookLocalLink(document, target, title) {
    if (!target || typeof target.id !== 'string' || !target.id) {
        throw new TypeError('Для перехода нужен заголовок с идентификатором.');
    }

    const link = document.createElement('a');

    link.textContent = title;
    link.href = `#${target.id}`;
    link.setAttribute('hx-boost', 'false');

    link.onclick = (event) => {
        if (!ordinaryActivation(event) || !target.isConnected) return;

        event.preventDefault();
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: 'start', inline: 'nearest', behavior: 'auto' });
    };

    return link;
}
