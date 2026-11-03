// frontend/src/js/shared/ui/sticky-navigation.js

const SCROLL_THRESHOLD = 10;
const SCROLLED_CLASS = 'navbar-main--scrolled';

let scrollBound = false;

function updateNavShadow() {
    document.querySelector('.main-nav')?.classList.toggle(SCROLLED_CLASS, window.scrollY > SCROLL_THRESHOLD);
}

export function initStickyNavigation() {
    updateNavShadow();

    if (scrollBound) return;
    scrollBound = true;

    window.addEventListener('scroll', updateNavShadow, { passive: true });
}