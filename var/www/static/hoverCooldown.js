const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerBoard ul.cardRow li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
].join(', ');

const OWN_SIDE_EXCLUSION_SELECTOR = '.enemyBoard, .enemyDeckHand';

const HOVER_SWITCH_COOLDOWN_MS = 500;

/**
 * Marker class applied to the managed container while the JS hover manager
 * is running. cards.css / cardDragDrop.css gate the own-side :hover rules
 * behind :not(.hover-managed) so the cooldown actually drives the visual
 * hover state (the :hover rules remain the no-JS / touch fallback, and
 * enemy-board hover stays instant).
 */
const HOVER_MANAGED_CLASS = 'hover-managed';

class CardHoverManager {
    constructor(container, { switchCooldownMs = HOVER_SWITCH_COOLDOWN_MS, now = () => performance.now() } = {}) {
        this.container = container;
        this.switchCooldownMs = switchCooldownMs;
        this.now = now;
        // Reduced-motion choice: disable the JS hover manager entirely. The
        // plain :hover fallback rules stay active and the :focus-within styles
        // are pure CSS, so keyboard focus visuals are unaffected.
        this.enabled = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.hoveredCard = null;
        this.lastSwitchAt = Number.NEGATIVE_INFINITY;
        this.frameHandle = null;
        this.pendingEvent = null;
        this.onMouseMove = null;
        this.applyPendingTarget = () => this.consumePendingTarget();
    }

    start() {
        if (!this.enabled || !this.container) return false;
        this.onMouseMove = (event) => this.handleMouseMove(event);
        this.container.addEventListener('mousemove', this.onMouseMove, { passive: true });
        this.container.classList.add(HOVER_MANAGED_CLASS);
        return true;
    }

    stop() {
        if (this.onMouseMove) {
            this.container.removeEventListener('mousemove', this.onMouseMove);
            this.onMouseMove = null;
        }
        this.container.classList.remove(HOVER_MANAGED_CLASS);
        if (this.frameHandle !== null) {
            window.cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.pendingEvent = null;
        this.clearHover();
    }

    handleMouseMove(event) {
        this.pendingEvent = event;
        if (this.frameHandle !== null) return;
        this.frameHandle = window.requestAnimationFrame(this.applyPendingTarget);
    }

    consumePendingTarget() {
        this.frameHandle = null;
        const event = this.pendingEvent;
        this.pendingEvent = null;
        if (!event) return;

        const target = this.resolveHoverTarget(event.target);
        if (target === this.hoveredCard) return;

        if (!target) {
            this.clearHover();
            return;
        }
        if (this.now() - this.lastSwitchAt < this.switchCooldownMs) return;

        this.swapHover(target);
        this.lastSwitchAt = this.now();
    }

    resolveHoverTarget(target) {
        if (!target || typeof target.closest !== 'function') return null;
        const card = target.closest(CARD_HOVER_TARGET_SELECTOR);
        if (!card || card.closest(OWN_SIDE_EXCLUSION_SELECTOR)) return null;
        return card;
    }

    swapHover(card) {
        if (this.hoveredCard) this.hoveredCard.classList.remove('card-hover');
        card.classList.add('card-hover');
        this.hoveredCard = card;
    }

    clearHover() {
        if (this.hoveredCard) this.hoveredCard.classList.remove('card-hover');
        this.hoveredCard = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
