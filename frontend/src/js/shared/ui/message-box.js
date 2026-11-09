// frontend/src/js/shared/ui/message-box.js

/**
 * Единый вывод сообщений в контейнер страницы.
 *
 * Раньше каждый раздел держал свою копию этой пары строк, из-за чего
 * поведение (класс ошибки, текст) приходилось править в десятке файлов.
 */

export function showBoxMessage(box, text, isError = false) {
    if (!box) return;

    box.textContent = text;
    box.classList.toggle('alert-error', Boolean(isError));
}

export function messageShower(box) {
    return (text, isError = false) => showBoxMessage(box, text, isError);
}
