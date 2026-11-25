const CARD_ZOOM_SCREEN_SELECTOR = '.playerScreen.zoomCards';
const ZOOM_CARD_SELECTOR =
    '.playerScreen .cardContainer:not(.ghost):not(.loading):not(.duplicate)';
const HOVERED_HOLOGRAM_SELECTOR = '.playerBoard ul.hologramRow .hologram';
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
        window.cardHoverManager.addHoverListener((hovered) => this.followHoveredCard(hovered));
        document.addEventListener(
            'keydown',
            (event) => {
                if (event.key === 'Escape') this.release();
            },
            true,
        );
        return true;
    }

    followHoveredCard(hovered) {
        const card = this.zoomCardForHoverTarget(hovered);
        if (card === this.zoomedCard) return;
        this.release();
        if (!card || card.classList.contains('faceDown')) return;
        this.showZoom(card);
    }

    zoomCardForHoverTarget(hovered) {
        if (!hovered) return null;
        if (hovered.matches(ZOOM_CARD_SELECTOR)) return hovered;
        if (!hovered.matches(HOVERED_HOLOGRAM_SELECTOR)) return null;
        return hovered.querySelector(ZOOM_CARD_SELECTOR);
    }

    showZoom(card) {
        const stage = document.createElement('div');
        stage.classList.add(ZOOM_STAGE_CLASS);
        const zoomedClone = card.cloneNode(true);
        zoomedClone.removeAttribute('tabindex');
        zoomedClone.querySelectorAll('[tabindex]').forEach((focusable) => {
            focusable.removeAttribute('tabindex');
        });
        stage.appendChild(zoomedClone);
        const viewportMin = Math.min(window.innerWidth, window.innerHeight);
        const zoomedCardHeight = (viewportMin * ZOOMED_CARD_VMIN_PERCENT) / 100;
        stage.style.setProperty('--card-zoom-scale', String(zoomedCardHeight / card.offsetHeight));
        this.screen.appendChild(stage);
        this.zoomStage = stage;
        this.zoomedCard = card;
        card.classList.add(ZOOM_CLASS);
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
