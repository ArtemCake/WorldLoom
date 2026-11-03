// frontend/public/js/theme-init.js

(function () {
    const allowedThemes = new Set(['dark-fantasy', 'light-fantasy', 'fantasy', 'custom']);
    let theme = 'dark-fantasy';

    try {
        const savedTheme = localStorage.getItem('user-theme');
        if (allowedThemes.has(savedTheme)) theme = savedTheme;
    } catch {
        // Недоступность хранилища не мешает применить тему по умолчанию.
    }

    const root = document.documentElement;
    root.classList.remove('theme-dark-fantasy', 'theme-light-fantasy', 'theme-fantasy');

    if (theme !== 'custom') {
        root.classList.add(`theme-${theme}`);
    }
})();