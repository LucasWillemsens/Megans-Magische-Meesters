const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerBoard .deck-stack .active-deck:not(.blocked) button.draw:not(.blocked):not(:disabled)',
    '.playerBoard ul.cardRow[title="cards"] li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
    '.enemyBoard li.cardContainer',
].join(', ');

const HOVER_REMOVE_COOLDOWN_MS = 500;
const HOVER_CLASS = 'card-hover';
const ZOOM_SCREEN_CLASS = 'zoomCards';

class CardHoverManager {
    constructor(container) {
        this.container = container;
        this.hoveredCard = null;
        this.onMouseMove = null;
        this.onMouseLeave = null;
        this.hoverListeners = [];
    }

    start() {
        if (!this.container) return false;
        this.onMouseMove = (event) => this.handleMouseMove(event);
        this.onMouseLeave = () => this.handleMouseLeave();
        this.container.addEventListener('mousemove', this.onMouseMove, { passive: true });
        this.container.addEventListener('mouseleave', this.onMouseLeave);
        if (this.container.classList.contains(ZOOM_SCREEN_CLASS)) {
            this.container.addEventListener('focusin', (event) => this.handleFocusIn(event));
            this.container.addEventListener('focusout', (event) => this.handleFocusOut(event));
        }
        return true;
    }

    addHoverListener(listener) {
        this.hoverListeners.push(listener);
        listener(this.hoveredCard);
    }

    notifyHoverListeners() {
        for (const listener of this.hoverListeners) {
            listener(this.hoveredCard);
        }
    }

    handleMouseMove(event) {
        const OnCoolDown = this.startedAt && (this.startedAt + HOVER_REMOVE_COOLDOWN_MS > Date.now());
        if (this.hoveredCard && !OnCoolDown) {
            if (this.hoveredCard !== event.target.closest(CARD_HOVER_TARGET_SELECTOR)) {
                this.releaseHover();
            }
        }
        let target = event.target;
        if (!target || typeof target.closest !== 'function') 
        {
            return;
        }
        if (!OnCoolDown) this.applyHover(target.closest(CARD_HOVER_TARGET_SELECTOR));
    }

    handleMouseLeave() {
        this.releaseHover();
    }

    handleFocusIn(event) {
        const target = this.focusHoverTarget(event.target);
        if (this.hoveredCard && this.hoveredCard !== target) this.clearAllHover();
        this.applyHover(target);
    }

    handleFocusOut(event) {
        if (!this.hoveredCard) return;
        if (this.focusHoverTarget(event.target) !== this.hoveredCard) return;
        if (this.focusHoverTarget(event.relatedTarget)) return;
        this.clearAllHover();
    }

    focusHoverTarget(element) {
        return element?.closest?.(CARD_HOVER_TARGET_SELECTOR) ?? null;
    }

    applyHover(card) {
        if (this.hoveredCard === card) return;
        card.classList.add(HOVER_CLASS);
        this.hoveredCard = card;
        this.startedAt = Date.now();
        this.notifyHoverListeners();
    }

    releaseHover() {
        const remainingMs = this.startedAt + HOVER_REMOVE_COOLDOWN_MS - Date.now();
        if (remainingMs <= 0) {
            this.clearAllHover();
            return;
        }
        window.setTimeout(() => this.clearAllHover(), remainingMs);
    }

    clearAllHover() {
        for (const card of this.container.querySelectorAll(`.${HOVER_CLASS}`)) {
            card.classList.remove(HOVER_CLASS);
        }
        this.hoveredCard = null;
        this.notifyHoverListeners();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
