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
        this.pendingTarget = null;
        this.pendingTimer = null;
        this.pendingClearTimer = null;
        this.hoverBounds = null;
        this.hoverShiftX = 0;
        this.hoverShiftY = 0;
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
        this.cancelPendingSwitch();
        this.cancelPendingClear();
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

        const target = this.resolveHoverTarget(event);
        if (target === this.hoveredCard) {
            this.cancelPendingSwitch();
            this.cancelPendingClear();
            return;
        }

        if (!target) {
            // The pointer left every hoverable (or sits over the gap the
            // hover lift just opened). Keep the current hover state for the
            // rest of the hold window instead of dropping it right away —
            // clearing immediately makes the card snap back down and flicker
            // when the pointer rests near its bottom edge.
            this.cancelPendingSwitch();
            this.schedulePendingClear();
            return;
        }

        this.cancelPendingClear();
        const elapsed = this.now() - this.lastSwitchAt;
        if (elapsed < this.switchCooldownMs) {
            // Inside the cooldown window: don't drop the switch — apply it
            // when the window expires, so the hover still lands on the card
            // the pointer stopped on (a dropped event would leave the old
            // card highlighted indefinitely).
            this.schedulePendingSwitch(target, this.switchCooldownMs - elapsed);
            return;
        }

        this.cancelPendingSwitch();
        this.swapHover(target);
        this.lastSwitchAt = this.now();
    }

    schedulePendingSwitch(target, waitMs) {
        this.cancelPendingSwitch();
        this.pendingTarget = target;
        this.pendingTimer = window.setTimeout(() => {
            this.pendingTimer = null;
            const pending = this.pendingTarget;
            this.pendingTarget = null;
            if (!pending || pending === this.hoveredCard) return;
            if (typeof pending.isConnected !== 'undefined' && !pending.isConnected) return;
            this.swapHover(pending);
            this.lastSwitchAt = this.now();
        }, waitMs);
    }

    cancelPendingSwitch() {
        if (this.pendingTimer !== null) {
            window.clearTimeout(this.pendingTimer);
            this.pendingTimer = null;
        }
        this.pendingTarget = null;
    }

    /**
     * Defer clearing the hover until the hold window (switchCooldownMs)
     * has elapsed since the hover state was applied. If the pointer comes
     * back over a hoverable before then, consumePendingTarget cancels the
     * pending clear and the state is kept.
     */
    schedulePendingClear() {
        if (this.pendingClearTimer !== null || !this.hoveredCard) return;
        const elapsed = this.now() - this.lastSwitchAt;
        const waitMs = Math.max(0, this.switchCooldownMs - elapsed);
        this.pendingClearTimer = window.setTimeout(() => {
            this.pendingClearTimer = null;
            this.clearHover();
        }, waitMs);
    }

    cancelPendingClear() {
        if (this.pendingClearTimer !== null) {
            window.clearTimeout(this.pendingClearTimer);
            this.pendingClearTimer = null;
        }
    }

    resolveHoverTarget(event) {
        const hovered = this.hoveredCard;
        if (hovered && this.hoverBounds) {
            if (typeof hovered.isConnected === 'undefined' || hovered.isConnected) {
                // Sticky hit-testing: the hover lift moves the card out from
                // under the pointer (e.g. a pointer resting near the card's
                // bottom edge). Keep treating the pointer as "on the card"
                // while it stays inside the card's pre-lift footprint —
                // recovered from the card's current rect so it stays correct
                // after page scrolling. Without this, the hover clears the
                // moment the card lifts, and the card snaps down, re-hovers,
                // lifts, and drops again in a visible flicker loop.
                const current = hovered.getBoundingClientRect();
                const left = current.left - this.hoverShiftX;
                const top = current.top - this.hoverShiftY;
                const right = left + this.hoverBounds.width;
                const bottom = top + this.hoverBounds.height;
                if (
                    event.clientX >= left && event.clientX <= right &&
                    event.clientY >= top && event.clientY <= bottom
                ) {
                    return hovered;
                }
            } else {
                this.clearHover();
            }
        }
        const target = event.target;
        if (!target || typeof target.closest !== 'function') return null;
        const card = target.closest(CARD_HOVER_TARGET_SELECTOR);
        if (!card || card.closest(OWN_SIDE_EXCLUSION_SELECTOR)) return null;
        return card;
    }

    swapHover(card) {
        if (this.hoveredCard) this.hoveredCard.classList.remove('card-hover');
        // Capture the card's pre-lift footprint and how far the hover lift
        // moves it, so sticky hit-testing above can reconstruct where the
        // card sits when un-hovered.
        const beforeRect = card.getBoundingClientRect();
        card.classList.add('card-hover');
        const afterRect = card.getBoundingClientRect();
        this.hoverBounds = beforeRect;
        this.hoverShiftX = afterRect.left - beforeRect.left;
        this.hoverShiftY = afterRect.top - beforeRect.top;
        this.hoveredCard = card;
    }

    clearHover() {
        this.cancelPendingSwitch();
        this.cancelPendingClear();
        if (this.hoveredCard) this.hoveredCard.classList.remove('card-hover');
        this.hoveredCard = null;
        this.hoverBounds = null;
        this.hoverShiftX = 0;
        this.hoverShiftY = 0;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
