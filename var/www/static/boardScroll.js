const SHORT_BOARD_VIEWPORT_QUERY = '(max-height: 48.125rem)';

document.addEventListener('DOMContentLoaded', () => {
    const turnPhase = document.getElementById('turnPhase')?.dataset.phase ?? '';
    if (turnPhase === 'enemy') return;
    if (!window.matchMedia(SHORT_BOARD_VIEWPORT_QUERY).matches) return;
    document.getElementById('playerBoard')?.scrollIntoView({ block: 'start' });
});
