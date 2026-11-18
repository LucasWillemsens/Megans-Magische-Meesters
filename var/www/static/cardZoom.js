const CARD_ZOOM_SCREEN_SELECTOR = '.playerScreen.zoomCards';
const ZOOM_CARD_SELECTOR =
    '.playerScreen .cardContainer:not(.ghost):not(.loading):not(.duplicate)';
const ZOOM_CLASS = 'card-zoomed';

class CardZoomManager {
    constructor(screen) {
        this.screen = screen;
        this.zoomedCard = null;
    }

    start() {
        if (!this.screen) return false;
        this.screen.addEventListener('mouseover', (event) => this.zoomCardFor(event));
        this.screen.addEventListener('mouseout', (event) => this.unzoomCardFor(event));
        document.addEventListener(
            'keydown',
            (event) => {
                if (event.key === 'Escape') this.release();
            },
            true,
        );
        return true;
    }

    zoomCardFor(event) {
        const card = event.target?.closest?.(ZOOM_CARD_SELECTOR) ?? null;
        if (!card || card === this.zoomedCard) return;
        if (this.zoomedCard) this.release();
        card.classList.add(ZOOM_CLASS);
        this.zoomedCard = card;
    }

    unzoomCardFor(event) {
        const card = event.target?.closest?.(ZOOM_CARD_SELECTOR) ?? null;
        if (!card || card !== this.zoomedCard) return;
        if (event.relatedTarget && card.contains(event.relatedTarget)) return;
        this.release();
    }

    release() {
        if (!this.zoomedCard) return false;
        this.zoomedCard.classList.remove(ZOOM_CLASS);
        this.zoomedCard = null;
        return true;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector(CARD_ZOOM_SCREEN_SELECTOR);
    if (!screen) return;
    window.cardZoomManager = new CardZoomManager(screen);
    window.cardZoomManager.start();
});
