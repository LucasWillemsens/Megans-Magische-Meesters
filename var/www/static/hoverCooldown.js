const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerScreen .deckHand .active-deck:not(.blocked) button.draw:not(.blocked):not(:disabled)',
    '.playerBoard ul.cardRow li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
    '.enemyBoard li.cardContainer',
].join(', ');

const HOVER_REMOVE_COOLDOWN_MS = 300;
const HOVER_CLASS = 'card-hover';

class CardHoverManager {
    constructor(container) {
        this.container = container;
        this.hoveredCard = null;
        this.frameHandle = null;
        this.pendingEvent = null;
        this.onMouseMove = null;
        this.onMouseLeave = null;
        this.applyPendingEvent = () => this.consumePendingEvent();
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
        if (this.frameHandle !== null) {
            window.cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.pendingEvent = null;
        this.clearAllHover();
    }

    handleMouseMove(event) {
        this.pendingEvent = event;
        if (this.frameHandle !== null) return;
        this.frameHandle = window.requestAnimationFrame(this.applyPendingEvent);
    }

    handleMouseLeave() {
        if (this.frameHandle !== null) {
            window.cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.pendingEvent = null;
        if (this.hoveredCard) {
            this.releaseHover();
        }
    }

    consumePendingEvent() {
        this.frameHandle = null;
        const event = this.pendingEvent;
        this.pendingEvent = null;
        if (!event) return;

        const target = this.resolveHoverTarget(event);
        if (!target) {
            if (this.hoveredCard) {
                this.releaseHover();
            }
            return;
        }
        this.applyHover(target);
    }

    resolveHoverTarget(event) {
        let target = this.hoveredCard;
        if (!target || this.startedAt + HOVER_REMOVE_COOLDOWN_MS <= Date.now()) {
            target = event.target;
        }
        if (!target || typeof target.closest !== 'function') return null;
        return target.closest(CARD_HOVER_TARGET_SELECTOR);
    }

    applyHover(card) {
        if (this.hoveredCard) { return;}
        card.classList.add(HOVER_CLASS);
        this.hoveredCard = card;
        this.startedAt = Date.now();
    }

    releaseHover() {
        const remainingMs = this.startedAt + HOVER_REMOVE_COOLDOWN_MS - Date.now();
        if (remainingMs <= 0) {
            this.clearAllHover();
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
