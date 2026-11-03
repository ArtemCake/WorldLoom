// frontend/src/js/features/users/profile.js

import { clearLegacyTokens } from '../auth/auth.js';
import { initAvatarPreview } from './avatar-preview.js';
import { requestProfile, runProfileAction, showProfileStatus, unexpectedProfileResponse } from './profile-actions.js';

const initializedForms = new WeakSet();
const ACTIONS = {
    details: { path: '/profile/update', method: 'PUT' },
    roles: { path: '/profile/roles', method: 'PATCH' },
    password: { path: '/profile/change-password', method: 'POST' },
    verification: { path: '/profile/resend-verification', method: 'POST' }
};

function lockSavedForm(form) {
    form.dataset.blocked = 'true';

    for (const control of form.querySelectorAll('button, input, select, textarea')) {
        control.disabled = true;
    }
}

async function submitProfileForm(form) {
    const kind = form.dataset.profileForm;
    const action = ACTIONS[kind];
    if (!action) return;

    const payload = new FormData(form);
    const avatar = payload.get('avatar');

    if (avatar instanceof File && !avatar.name) payload.delete('avatar');

    const box = form.querySelector('[data-profile-message]');

    await runProfileAction(form, box, async () => {
        const data = await requestProfile(action.path, action.method, payload);
        if (typeof data.message !== 'string' || !data.message) throw unexpectedProfileResponse();

        if (kind === 'password') {
            form.reset();
            lockSavedForm(form);
            clearLegacyTokens();
            window.location.assign('/login');
            return;
        }

        let message = data.message;

        if (kind === 'details' || kind === 'roles') {
            message += ' Обновите данные страницы по ссылке сверху, чтобы увидеть актуальное меню и состояние профиля.';
            lockSavedForm(form);
        }

        showProfileStatus(box, message, true);
    });
}

export function initProfile() {
    const root = document.querySelector('[data-profile-root]');
    if (!root) return;

    initAvatarPreview(root);

    for (const form of root.querySelectorAll('form[data-profile-form]')) {
        if (initializedForms.has(form)) continue;
        initializedForms.add(form);

        form.addEventListener('submit', (event) => {
            event.preventDefault();
            void submitProfileForm(form);
        });
    }
}