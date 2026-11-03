// frontend/src/js/features/auth/mfa-setup.js

import { requestProfile, runProfileAction, showProfileStatus, unexpectedProfileResponse } from '../users/profile-actions.js';

const initializedRoots = new WeakSet();

function setVisible(element, visible) {
    if (!element) return;
    element.hidden = !visible;
    element.classList.toggle('hidden', !visible);
}

function downloadBackupCodes(codes) {
    const text = 'Резервные коды двухфакторной аутентификации WorldLoom\n\n' + codes.join('\n')
        + '\n\nКаждый код можно использовать только один раз. Храните файл в надёжном месте.';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = 'worldloom-backup-codes.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function renderSetup(data, block, secret, canvas) {
    if (typeof data.secret !== 'string' || !data.secret || typeof data.otpauth_uri !== 'string') {
        throw unexpectedProfileResponse();
    }

    let uri;

    try {
        uri = new URL(data.otpauth_uri);
    } catch {
        throw unexpectedProfileResponse();
    }

    if (uri.protocol !== 'otpauth:' || uri.hostname !== 'totp') throw unexpectedProfileResponse();

    secret.textContent = data.secret;
    setVisible(block, true);
    canvas.hidden = true;

    if (typeof window.QRCode?.toCanvas === 'function') {
        try {
            await window.QRCode.toCanvas(canvas, data.otpauth_uri, { width: 220 });
            canvas.hidden = false;
        } catch {
            canvas.hidden = true;
        }
    }
}

export function initMfaSetup() {
    const root = document.querySelector('[data-mfa-root]');
    if (!root || initializedRoots.has(root)) return;
    initializedRoots.add(root);

    const status = root.querySelector('#mfa-status');
    const start = root.querySelector('#mfa-start-setup');
    const setup = root.querySelector('#mfa-setup-block');
    const secret = root.querySelector('#mfa-manual-secret');
    const canvas = root.querySelector('#mfa-qr-canvas');
    const confirm = root.querySelector('#mfa-confirm-form');
    const disable = root.querySelector('#mfa-disable-form');
    const backupList = root.querySelector('#mfa-backup-codes');
    const backupWrapper = root.querySelector('#mfa-backup-wrapper');

    let completed = false;
    let backupCodes = [];

    start?.addEventListener('click', async () => {
        if (completed || !setup || !secret || !canvas) return;

        const ok = await runProfileAction(root, status, async () => {
            const data = await requestProfile('/profile/mfa/setup', 'POST', new FormData());
            await renderSetup(data, setup, secret, canvas);
            showProfileStatus(status, 'Секрет подготовлен. Добавьте его в приложение и подтвердите кодом.', true);
        });

        if (ok) start.disabled = true;
    });

    confirm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (completed || !backupList || !backupWrapper) return;

        const payload = new FormData(confirm);

        const ok = await runProfileAction(root, status, async () => {
            const data = await requestProfile('/profile/mfa/confirm', 'POST', payload);

            if (!Array.isArray(data.backup_codes) || !data.backup_codes.length
                || !data.backup_codes.every((code) => typeof code === 'string' && code.length > 0)) {
                throw unexpectedProfileResponse();
            }

            backupCodes = [...data.backup_codes];

            const items = backupCodes.map((value) => {
                const item = document.createElement('li');
                const code = document.createElement('code');

                code.textContent = value;
                item.appendChild(code);
                return item;
            });

            backupList.replaceChildren(...items);
            setVisible(backupWrapper, true);
            showProfileStatus(status, 'Двухфакторная аутентификация включена. Сохраните резервные коды.', true);
        });

        if (!ok) return;

        completed = true;
        confirm.reset();
        secret.textContent = '';
        canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
        setVisible(setup, false);
        setVisible(start, false);
    });

    root.querySelector('#mfa-backup-download')?.addEventListener('click', () => {
        if (backupCodes.length) downloadBackupCodes(backupCodes);
    });

    root.querySelector('#mfa-backup-ack')?.addEventListener('click', () => {
        if (!completed) return;

        backupCodes = [];
        backupList.replaceChildren();
        window.location.reload();
    });

    disable?.addEventListener('submit', async (event) => {
        event.preventDefault();

        const payload = new FormData(disable);

        const ok = await runProfileAction(root, status, async () => {
            const data = await requestProfile('/profile/mfa/disable', 'POST', payload);
            if (typeof data.message !== 'string') throw unexpectedProfileResponse();

            disable.reset();
            showProfileStatus(status, data.message, true);
        });

        if (ok) window.location.reload();
    });
}