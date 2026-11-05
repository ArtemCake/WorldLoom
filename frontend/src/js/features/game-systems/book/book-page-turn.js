//frontend/src/js/features/game-systems/book/book-page-turn.js

function createSnapshot(spread) {
	const snapshot = spread.cloneNode(true);
	const sourceControls = spread.querySelectorAll('input, textarea, select');
	const targetControls = snapshot.querySelectorAll('input, textarea, select');

	sourceControls.forEach((source, index) => {
		const target = targetControls[index];

		if (source instanceof HTMLInputElement && target instanceof HTMLInputElement) {
			target.value = source.value;
			target.checked = source.checked;
		}

		if (source instanceof HTMLTextAreaElement && target instanceof HTMLTextAreaElement) {
			target.value = source.value;
			target.textContent = source.value;
		}

		if (source instanceof HTMLSelectElement && target instanceof HTMLSelectElement) {
			target.selectedIndex = source.selectedIndex;
		}
	});

	snapshot.querySelectorAll('.rules-book__corner').forEach((control) => control.remove());

	for (const element of [snapshot, ...snapshot.querySelectorAll('*')]) {
		element.removeAttribute('id');
		element.removeAttribute('name');
		element.removeAttribute('autofocus');
	}

	snapshot.classList.add('rules-book__snapshot');
	snapshot.setAttribute('aria-hidden', 'true');
	snapshot.inert = true;

	return snapshot;
}

export function createBookPageTurn(book, spread, {signal} = {}) {
	let busy = false;

	async function turn(direction, navigate) {
		if (busy || signal?.aborted) return false;

		busy = true;

		let layer = null;
		let animation = null;
		let focused = null;
		let locked = false;
		let previousInert = false;

		const abort = () => animation?.cancel();

		try {
			const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
			const rectangle = spread.getBoundingClientRect();
			const narrow = window.matchMedia('(max-width: 720px)').matches;
			const canAnimate = !reducedMotion && !narrow && rectangle.width > 0 && typeof spread.animate === 'function';
			const snapshot = canAnimate ? createSnapshot(spread) : null;

			const pageScrollPositions = [...spread.querySelectorAll(':scope > .rules-book__page')].map((page) => ({
				top: page.scrollTop,
				left: page.scrollLeft
			}));

			// navigate возвращает false, если переход отменён или страницы нет.
			const changed = navigate();

			if (!changed) return false;
			if (!canAnimate || signal?.aborted) return true;

			focused = document.activeElement;
			previousInert = book.inert;
			book.inert = true;
			locked = true;

			layer = document.createElement('div');
			layer.className = 'rules-book__turn-layer';
			layer.setAttribute('aria-hidden', 'true');
			layer.inert = true;

			const leaf = document.createElement('div');
			leaf.className = 'rules-book__turn-leaf';
			leaf.classList.add(direction === 1 ? 'rules-book__turn-leaf--next' : 'rules-book__turn-leaf--previous');

			const front = document.createElement('div');
			front.className = 'rules-book__turn-front';

			const back = document.createElement('div');
			back.className = 'rules-book__turn-back';

			snapshot.style.width = `${rectangle.width}px`;
			snapshot.style.height = `${rectangle.height}px`;
			snapshot.style.left = direction === 1 ? '-100%' : '0';

			front.append(snapshot);
			leaf.append(front, back);
			layer.append(leaf);
			spread.append(layer);

			const snapshotPages = snapshot.querySelectorAll(':scope > .rules-book__page');

			snapshotPages.forEach((page, index) => {
				const position = pageScrollPositions[index];

				if (!position) return;

				page.scrollTop = position.top;
				page.scrollLeft = position.left;
			});

			const angle = direction === 1 ? -180 : 180;

			animation = leaf.animate([
				{transform: 'rotateY(0deg)', opacity: 1, offset: 0},
				{transform: `rotateY(${angle * 0.85}deg)`, opacity: 1, offset: 0.85},
				{transform: `rotateY(${angle}deg)`, opacity: 0, offset: 1}
			], {
				duration: 900,
				easing: 'cubic-bezier(0.42, 0, 0.58, 1)',
				fill: 'forwards'
			});

			signal?.addEventListener('abort', abort, {once: true});

			if (signal?.aborted) animation.cancel();

			try {
				await animation.finished;
			} catch (error) {
				if (error?.name !== 'AbortError') throw error;
			}

			return true;
		} finally {
			signal?.removeEventListener('abort', abort);
			animation?.cancel();
			layer?.remove();

			if (locked) {
				book.inert = previousInert;

				if (!signal?.aborted && !book.inert && focused instanceof HTMLElement && focused.isConnected) {
					focused.focus({preventScroll: true});
				}
			}

			busy = false;
		}
	}

	return {turn, isBusy: () => busy};
}