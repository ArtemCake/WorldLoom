// frontend/src/js/features/auth/password-toggle.js

export function initPasswordToggles(root = document) {
    const fields = root.querySelectorAll('input[type="password"]:not([data-toggle-bound])');

    for (const input of fields) {
        input.dataset.toggleBound = 'true';

        const wrapper = document.createElement('div');
        wrapper.className = 'password-field';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'password-toggle';
        button.textContent = '👁';
        button.setAttribute('aria-label', 'Показать пароль');
        button.setAttribute('aria-pressed', 'false');

        button.addEventListener('click', () => {
            const visible = input.type === 'password';
            input.type = visible ? 'text' : 'password';
            button.textContent = visible ? '🙈' : '👁';
            button.setAttribute('aria-label', visible ? 'Скрыть пароль' : 'Показать пароль');
            button.setAttribute('aria-pressed', String(visible));
        });

        wrapper.appendChild(button);
    }
}