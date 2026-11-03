// frontend/src/js/features/users/avatar-preview.js

import { showProfileStatus } from './profile-actions.js';

const initializedInputs = new WeakSet();

export function initAvatarPreview(root = document) {
    const input = root.querySelector('#avatar-input');
    const image = root.querySelector('[data-avatar-preview]');
    const button = root.querySelector('[data-avatar-select]');

    if (!input || !image || !button || initializedInputs.has(input)) return;
    initializedInputs.add(input);

    const originalSource = image.getAttribute('src');
    const box = input.form?.querySelector('[data-profile-message]');

    button.addEventListener('click', () => input.click());

    input.addEventListener('change', () => {
        const file = input.files?.[0];

        if (!file) {
            image.setAttribute('src', originalSource);
            return;
        }

        const reader = new FileReader();

        reader.addEventListener('load', () => {
            if (input.files?.[0] !== file || !input.isConnected || typeof reader.result !== 'string') return;
            image.src = reader.result;
        });

        reader.addEventListener('error', () => {
            if (input.files?.[0] !== file) return;

            input.value = '';
            image.setAttribute('src', originalSource);
            showProfileStatus(box, 'Не удалось прочитать выбранный файл. Выберите изображение заново.');
        });

        reader.readAsDataURL(file);
    });
}