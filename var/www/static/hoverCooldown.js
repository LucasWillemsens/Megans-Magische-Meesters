const CARD_HOVER_TARGET_SELECTOR = [
    '.playerScreen .deckHand .hand li.cardContainer',
    '.playerScreen .deckHand .active-deck:not(.blocked) button.draw:not(.blocked):not(:disabled)',
    '.playerBoard ul.cardRow li.cardContainer',
    '.playerBoard ul.hologramRow .hologram',
    '.enemyBoard li.cardContainer',
].join(', ');

/**
 * Removal cooldown for quick pass-overs, anchored at the moment the hover
 * class is first applied to an element. Leaving after the window has expired
 * means the hover was deliberate, so the class comes off immediately with no
 * timer. Leaving inside the window is the flicker case (the animated lift
 * just moved the card out from under the pointer), so the class stays on
 * only until the anchored deadline: removal happens at most this long after
 * first hover. Movement over the element never refreshes the window.
 */
const HOVER_REMOVE_COOLDOWN_MS = 120;

/**
 * Single source of hover truth: the stylesheets carry no native pseudo-class
 * hover rules for cards, so this managed class is the only way a card reacts
 * to the pointer. The manager runs unconditionally and the hover transitions
 * always animate; there is no reduced-motion special-casing.
 */
const HOVER_CLASS = 'card-hover';

/**
 * Applies the managed hover class to whatever card surface the pointer is on.
 * Each element carries a hover episode that starts when the class is first
 * applied (stamped via performance.now()) and ends when the class is actually
 * removed. At most one element is actively hovered; cards abandoned inside
 * their cooldown window keep the class for the remainder of that window, so
 * a quick pass-over trails for at most HOVER_REMOVE_COOLDOWN_MS after its
 * first hover while a deliberate hover disappears the instant it is left.
 */
class CardHoverManager {
    constructor(container) {
        this.container = container;
        this.hoveredCard = null;
        this.episodes = new Map();
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
        // The pointer left the whole screen, so any queued mousemove is
        // stale; the hovered card goes through the normal release rule.
        if (this.frameHandle !== null) {
            window.cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.pendingEvent = null;
        if (this.hoveredCard) {
            this.releaseHover(this.hoveredCard);
            this.hoveredCard = null;
        }
    }

    consumePendingEvent() {
        this.frameHandle = null;
        const event = this.pendingEvent;
        this.pendingEvent = null;
        if (!event) return;

        const target = this.resolveHoverTarget(event);
        if (target === this.hoveredCard) return;
        if (!target) {
            if (this.hoveredCard) {
                this.releaseHover(this.hoveredCard);
                this.hoveredCard = null;
            }
            return;
        }
        this.swapHover(target);
    }

    resolveHoverTarget(event) {
        const hovered = this.hoveredCard;
        if (hovered && hovered.isConnected === false) {
            this.removeHoverNow(hovered);
        }
        const target = event.target;
        if (!target || typeof target.closest !== 'function') return null;
        return target.closest(CARD_HOVER_TARGET_SELECTOR);
    }

    /**
     * Moves the hover to another card: the new card gets the class
     * immediately (hover-in is never delayed) and the abandoned card is
     * released by the cooldown rule — instantly when it was hovered
     * deliberately, as a short trail when it was only passed over.
     */
    swapHover(card) {
        if (this.hoveredCard === card) return;
        if (this.hoveredCard) this.releaseHover(this.hoveredCard);
        this.applyHover(card);
        this.hoveredCard = card;
    }

    /**
     * Starts an episode by stamping it and adding the class, or resumes a
     * trailing one: a card whose class is still on keeps its original stamp
     * and only has its pending removal cancelled.
     */
    applyHover(card) {
        const episode = this.episodes.get(card);
        if (episode) {
            this.cancelScheduledRemove(episode);
            return;
        }
        this.episodes.set(card, { startedAt: performance.now(), timerId: null });
        card.classList.add(HOVER_CLASS);
    }

    /**
     * Ends the active hover of a card that was just left. Once its anchored
     * window has expired the class comes off immediately; inside the window
     * the removal is scheduled once for the remaining time, and further
     * movement outside never postpones it.
     */
    releaseHover(card) {
        const episode = this.episodes.get(card);
        if (!episode || episode.timerId !== null) return;
        const remainingMs = episode.startedAt + HOVER_REMOVE_COOLDOWN_MS - performance.now();
        if (remainingMs <= 0) {
            this.removeHoverNow(card);
            return;
        }
        episode.timerId = window.setTimeout(() => this.removeHoverNow(card), remainingMs);
    }

    removeHoverNow(card) {
        const episode = this.episodes.get(card);
        if (episode) this.cancelScheduledRemove(episode);
        this.episodes.delete(card);
        card.classList.remove(HOVER_CLASS);
        if (this.hoveredCard === card) this.hoveredCard = null;
    }

    cancelScheduledRemove(episode) {
        if (episode.timerId !== null) {
            window.clearTimeout(episode.timerId);
            episode.timerId = null;
        }
    }

    clearAllHover() {
        for (const card of Array.from(this.episodes.keys())) {
            this.removeHoverNow(card);
        }
        this.episodes.clear();
        this.hoveredCard = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.playerScreen');
    if (!screen) return;
    window.cardHoverManager = new CardHoverManager(screen);
    window.cardHoverManager.start();
});
