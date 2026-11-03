// frontend/src/js/features/users/delete-account.js

import { clearLegacyTokens } from '../auth/auth.js';
import { requestProfile, runProfileAction, unexpectedProfileResponse } from './profile-actions.js';

const initializedRoots = new WeakSet();

function setVisible(element, visible) {
    element.hidden = !visible;
    element.classList.toggle('hidden', !visible);
}

export function initDeleteAccountModal() {
    const root = document.querySelector('[data-profile-root]');
    const first = root?.querySelector('#delete-modal-step1');
    const second = root?.querySelector('#delete-modal-step2');
    const form = root?.querySelector('#delete-account-form');

    if (!root || !first || !second || !form || initializedRoots.has(root)) return;
    initializedRoots.add(root);

    const box = root.querySelector('#message-box-delete');
    const password = form.querySelector('[name="password"]');

    let activeModal = null;
    let opener = null;
    let previousOverflow = '';

    function openModal(modal) {
        if (!activeModal) {
            opener = document.activeElement;
            previousOverflow = document.body.style.overflow;
        }

        setVisible(first, modal === first);
        setVisible(second, modal === second);
        activeModal = modal;
        document.body.style.overflow = 'hidden';
        modal.querySelector('input:not(:disabled), button:not(:disabled)')?.focus();
    }

    function closeModals() {
        if (form.dataset.busy === 'true') return;

        setVisible(first, false);
        setVisible(second, false);
        activeModal = null;
        document.body.style.overflow = previousOverflow;
        password.value = '';

        if (form.dataset.blocked !== 'true') box.replaceChildren();
        if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    }

    root.addEventListener('click', (event) => {
        const button = event.target instanceof Element ? event.target.closest('[data-delete-action]') : null;
        if (!button || !root.contains(button)) return;

        event.preventDefault();
        if (form.dataset.busy === 'true') return;

        if (button.dataset.deleteAction === 'open-step1') openModal(first);
        else if (button.dataset.deleteAction === 'open-step2') openModal(second);
        else if (button.dataset.deleteAction === 'close') closeModals();
    });

    root.addEventListener('keydown', (event) => {
        if (!activeModal) return;

        if (event.key === 'Escape') {
            event.preventDefault();
            closeModals();
            return;
        }

        if (event.key !== 'Tab') return;

        const controls = [...activeModal.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]')];
        const firstControl = controls[0];
        const lastControl = controls.at(-1);

        if (!firstControl) {
            event.preventDefault();
            activeModal.focus();
        } else if (event.shiftKey && (document.activeElement === firstControl || !controls.includes(document.activeElement))) {
            event.preventDefault();
            lastControl.focus();
        } else if (!event.shiftKey && (document.activeElement === lastControl || !controls.includes(document.activeElement))) {
            event.preventDefault();
            firstControl.focus();
        }
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const submitter = event.submitter;
        if (!(submitter instanceof HTMLButtonElement) || !['true', 'false'].includes(submitter.value)) return;

        const payload = new FormData(form);
        payload.set('permanent', submitter.value);

        await runProfileAction(form, box, async () => {
            const data = await requestProfile('/auth/delete-account', 'POST', payload);
            if (typeof data.message !== 'string') throw unexpectedProfileResponse();

            form.dataset.blocked = 'true';
            password.value = '';
            clearLegacyTokens();
            window.location.assign('/login');
        });
    });
}