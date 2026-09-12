const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerBoard ul.cardRow li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
].join(', ');

const OWN_SIDE_EXCLUSION_SELECTOR = '.enemyBoard, .enemyDeckHand';

/**
 * The hover state is removed only after this delay has elapsed since the
 * cursor moved outside the hovered card (and its sticky resting footprint).
 * Re-entering inside the window cancels the removal; switching to a
 * different card is always immediate.
 */
const HOVER_REMOVE_DELAY_MS = 500;

/**
 * Marker class applied to the managed container while the JS hover manager
 * is running. cards.css / cardDragDrop.css gate the own-side :hover rules
 * behind :not(.hover-managed) so a single .card-hover class drives the
 * visual hover state (the :hover rules remain the no-JS / touch fallback,
 * and enemy-board hover stays instant).
 */
const HOVER_MANAGED_CLASS = 'hover-managed';

const HOVER_CLASS = 'card-hover';

class CardHoverManager {
    constructor(container, { removeDelayMs = HOVER_REMOVE_DELAY_MS } = {}) {
        this.container = container;
        this.removeDelayMs = removeDelayMs;
        // Reduced-motion choice: disable the JS hover manager entirely. The
        // plain :hover fallback rules stay active and the :focus-within styles
        // are pure CSS, so keyboard focus visuals are unaffected.
        this.enabled = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.hoveredCard = null;
        this.hoverFootprint = null;
        this.frameHandle = null;
        this.pendingEvent = null;
        this.removeTimer = null;
        this.onMouseMove = null;
        this.onMouseLeave = null;
        this.applyPendingEvent = () => this.consumePendingEvent();
    }

    start() {
        if (!this.enabled || !this.container) return false;
        this.onMouseMove = (event) => this.handleMouseMove(event);
        this.onMouseLeave = () => this.handleMouseLeave();
        this.container.addEventListener('mousemove', this.onMouseMove, { passive: true });
        this.container.addEventListener('mouseleave', this.onMouseLeave);
        this.container.classList.add(HOVER_MANAGED_CLASS);
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
        this.frameHandle = window.requestAnimationFrame(this.applyPendingEvent);
    }

    handleMouseLeave() {
        // The pointer left the screen: any queued mousemove is stale and must
        // not cancel the deferred removal.
        if (this.frameHandle !== null) {
            window.cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.pendingEvent = null;
        this.schedulePendingRemove();
    }

    consumePendingEvent() {
        this.frameHandle = null;
        const event = this.pendingEvent;
        this.pendingEvent = null;
        if (!event) return;

        const target = this.resolveHoverTarget(event);
        if (target === this.hoveredCard) {
            this.cancelPendingRemove();
            return;
        }
        if (!target) {
            this.schedulePendingRemove();
            return;
        }
        // Genuine cursor movement onto a different card switches immediately.
        this.swapHover(target);
    }

    resolveHoverTarget(event) {
        const hovered = this.hoveredCard;
        if (hovered) {
            if (hovered.isConnected === false) {
                this.clearHover();
            } else if (this.isInsideHoverFootprint(event)) {
                return hovered;
            }
        }
        const target = event.target;
        if (!target || typeof target.closest !== 'function') return null;
        const card = target.closest(CARD_HOVER_TARGET_SELECTOR);
        if (!card || card.closest(OWN_SIDE_EXCLUSION_SELECTOR)) return null;
        return card;
    }

    /**
     * Sticky hit-test against the hovered card's resting footprint, in page
     * coordinates so it stays correct while the page scrolls. The hover lift
     * is an animated transform, so the card can move out from under a
     * stationary near-edge pointer; while the pointer stays inside the area
     * the card occupies at rest it still counts as hovering, and the lift can
     * never re-arm a leave/enter flicker loop.
     */
    isInsideHoverFootprint(event) {
        const footprint = this.hoverFootprint;
        if (!footprint) return false;
        return (
            event.pageX >= footprint.left && event.pageX <= footprint.right &&
            event.pageY >= footprint.top && event.pageY <= footprint.bottom
        );
    }

    /**
     * Moves the hover state to another card. The class is removed from the
     * previous holder before it is added to the new one, so exactly one
     * element on screen carries it at any time.
     */
    swapHover(card) {
        this.cancelPendingRemove();
        if (this.hoveredCard === card) return;
        if (this.hoveredCard) this.hoveredCard.classList.remove(HOVER_CLASS);
        this.hoverFootprint = this.captureFootprint(card);
        card.classList.add(HOVER_CLASS);
        this.hoveredCard = card;
    }

    captureFootprint(card) {
        // Captured before the class is applied: the rect is the card's
        // resting position, untouched by the (transitioning) hover lift.
        const rect = card.getBoundingClientRect();
        const left = rect.left + window.scrollX;
        const top = rect.top + window.scrollY;
        return { left, top, right: left + rect.width, bottom: top + rect.height };
    }

    schedulePendingRemove() {
        if (this.removeTimer !== null || !this.hoveredCard) return;
        this.removeTimer = window.setTimeout(() => {
            this.removeTimer = null;
            this.clearHover();
        }, this.removeDelayMs);
    }

    cancelPendingRemove() {
        if (this.removeTimer !== null) {
            window.clearTimeout(this.removeTimer);
            this.removeTimer = null;
        }
    }

    clearHover() {
        this.cancelPendingRemove();
        if (this.hoveredCard) this.hoveredCard.classList.remove(HOVER_CLASS);
        this.hoveredCard = null;
        this.hoverFootprint = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
