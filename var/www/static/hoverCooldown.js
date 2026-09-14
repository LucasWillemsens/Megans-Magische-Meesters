const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerScreen .deckHand .active-deck:not(.blocked) button.draw:not(.blocked):not(:disabled)',
    '.playerBoard ul.cardRow[title="cards"] li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
    '.enemyBoard li.cardContainer',
].join(', ');

const HOVER_REMOVE_COOLDOWN_MS = 500;
const HOVER_CLASS = 'card-hover';

class CardHoverManager {
    constructor(container) {
        this.container = container;
        this.hoveredCard = null;
        this.onMouseMove = null;
        this.onMouseLeave = null;
    }

    start() {
        if (!this.container) return false;
        this.onMouseMove = (event) => this.handleMouseMove(event);
        this.onMouseLeave = () => this.handleMouseLeave();
        this.container.addEventListener('mousemove', this.onMouseMove, { passive: true });
        this.container.addEventListener('mouseleave', this.onMouseLeave);
        return true;
    }

    stop() {
        if (this.onMouseMove) {
            this.container.removeEventListener('mousemove', this.onMouseMove);
            this.onMouseMove = null;
        }
        if (this.onMouseLeave) {
            this.container.removeEventListener('mouseleave', this.onMouseLeave);
            this.onMouseLeave = null;
        }
        this.clearAllHover();
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

    applyHover(card) {
        if (this.hoveredCard === card) return;
        card.classList.add(HOVER_CLASS);
        this.hoveredCard = card;
        this.startedAt = Date.now();
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
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
