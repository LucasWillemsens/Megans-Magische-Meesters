const CARD_ZOOM_SCREEN_SELECTOR = '.playerScreen.zoomCards';
const ZOOM_CARD_SELECTOR =
    '.playerScreen .cardContainer:not(.ghost):not(.loading):not(.duplicate)';
const ZOOM_CLASS = 'card-zoomed';
const ZOOM_STAGE_CLASS = 'cardZoomStage';
const ZOOMED_CARD_VMIN_PERCENT = 70;

class CardZoomManager {
    constructor(screen) {
        this.screen = screen;
        this.zoomedCard = null;
        this.zoomStage = null;
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
        this.release();
        if (card.classList.contains('faceDown')) return;
        const stage = document.createElement('div');
        stage.classList.add(ZOOM_STAGE_CLASS);
        stage.appendChild(card.cloneNode(true));
        const viewportMin = Math.min(window.innerWidth, window.innerHeight);
        const zoomedCardHeight = (viewportMin * ZOOMED_CARD_VMIN_PERCENT) / 100;
        stage.style.setProperty('--card-zoom-scale', String(zoomedCardHeight / card.offsetHeight));
        this.screen.appendChild(stage);
        this.zoomStage = stage;
        this.zoomedCard = card;
        card.classList.add(ZOOM_CLASS);
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
        this.zoomStage.remove();
        this.zoomStage = null;
        return true;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector(CARD_ZOOM_SCREEN_SELECTOR);
    if (!screen) return;
    window.cardZoomManager = new CardZoomManager(screen);
    window.cardZoomManager.start();
});
