class LaneCardStacking {
    static OVERFLOW_ROW_CLASS = 'overflow-row';
    static MAX_CARDS_PER_ROW = 25;
    static BOARD_LANE_SELECTOR =
        '.playerBoard .lane, ul.enemyBoards li.enemyBoard ul.lanes li.lane';

    constructor() {
        this.debounceTimer = null;
        this.overlapOffset = 1.4;
        this.init();
    }

    init() {
        this.reflowAll();
        window.addEventListener('resize', () => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => this.reflowAll(), 300);
        });
    }

    reflowAll() {
        const lanes = document.querySelectorAll(LaneCardStacking.BOARD_LANE_SELECTOR);
        lanes.forEach(lane => this.reflowLane(lane));
    }

    reflowLane(lane) {
        const cardRows = lane.querySelectorAll(':scope > ul.cardRow');
        cardRows.forEach(row => this.reflowRowGroup(lane, row));
        const holoRows = lane.querySelectorAll(':scope > ul.hologramRow');
        holoRows.forEach(row => this.reflowRowGroup(lane, row));
    }

    reflowRowGroup(lane, row) {
        this.ensureSingleRow(row);

        const children = Array.from(row.children);
        if (children.length === 0) return;

        const laneWidth = lane.clientWidth;
        if (laneWidth <= 0) return;

        const emSize = parseFloat(getComputedStyle(lane).fontSize) || 16;
        const overlapPx = this.overlapOffset * emSize;
        const firstCardWidth = children[0].offsetWidth || 100;

        const cardsPerRow = Math.min(
            LaneCardStacking.MAX_CARDS_PER_ROW,
            Math.max(1, Math.floor((laneWidth - firstCardWidth) / overlapPx) + 1)
        );
        row.dataset.cardsPerRow = String(cardsPerRow);

        if (children.length > cardsPerRow) {
            this.splitIntoRows(row, children, cardsPerRow);
        }
    }

    ensureSingleRow(row) {
        let sibling = row.nextElementSibling;
        while (sibling) {
            const isOverflow = sibling.tagName === row.tagName
                && sibling.classList.contains(LaneCardStacking.OVERFLOW_ROW_CLASS);
            if (!isOverflow) break;
            const next = sibling.nextElementSibling;
            while (sibling.firstChild) {
                row.appendChild(sibling.firstChild);
            }
            sibling.remove();
            sibling = next;
        }
    }

    splitIntoRows(sourceRow, children, cardsPerRow) {
        const parent = sourceRow.parentNode;
        if (!parent) return;

        const rows = [sourceRow];
        for (let i = cardsPerRow; i < children.length; i += cardsPerRow) {
            const newRow = document.createElement('ul');
            newRow.className = [sourceRow.className, LaneCardStacking.OVERFLOW_ROW_CLASS]
                .filter(Boolean)
                .join(' ');
            newRow.title = sourceRow.title;
            rows.push(newRow);
        }

        children.forEach((child, index) => {
            const rowIndex = Math.min(Math.floor(index / cardsPerRow), rows.length - 1);
            rows[rowIndex].appendChild(child);
        });

        for (let i = 1; i < rows.length; i++) {
            rows[i].style.setProperty('--overflow-row-index', String(i));
            sourceRow.parentNode.insertBefore(rows[i], sourceRow);
        }
    }
}

class BoardViewportFit {
    static SMALL_VIEWPORT_MAX_HEIGHT = 768;
    static ENEMY_BOARD_SELECTOR = '.playerScreen ul.enemyBoards li.enemyBoard';
    static ENEMY_ZONE_SELECTOR = '.playerScreen ul.enemyBoards';
    static PLAYER_ZONE_SELECTORS = [
        '.playerScreen .players',
        '.playerScreen li.playerBoard',
        '.playerScreen .deckHand',
    ];
    static COMPACT_CLASS = 'enemy-board-fit-compact';
    static OVERLAP_HIDDEN_CLASS = 'enemy-board-fit-hidden';
    static RESIZE_RECHECK_MS = 200;
    static SETTLE_RECHECK_MS = 200;

    constructor(stacking) {
        this.stacking = stacking;
        this.resizeTimer = null;
        this.settleTimer = null;
        this.init();
    }

    init() {
        this.apply();
        window.addEventListener('resize', () => {
            clearTimeout(this.resizeTimer);
            this.resizeTimer = setTimeout(() => this.apply(), BoardViewportFit.RESIZE_RECHECK_MS);
        });
        if (document.readyState !== 'complete') {
            window.addEventListener('load', () => this.scheduleSettleRecheck(), { once: true });
        }
        this.scheduleSettleRecheck();
    }

    scheduleSettleRecheck() {
        clearTimeout(this.settleTimer);
        this.settleTimer = setTimeout(
            () => this.apply(),
            BoardViewportFit.SETTLE_RECHECK_MS,
        );
    }

    apply() {
        this.revealEnemyBoards();
        this.stacking?.reflowAll();
        const enemyZone = document.querySelector(BoardViewportFit.ENEMY_ZONE_SELECTOR);
        if (!enemyZone || !this.smallViewport()) return;
        if (!this.boardsShareShortViewport()) return;
        enemyZone.classList.add(BoardViewportFit.COMPACT_CLASS);
        if (!this.boardsShareShortViewport()) return;
        enemyZone.classList.remove(BoardViewportFit.COMPACT_CLASS);
        this.collapseEnemyBoards();
    }

    revealEnemyBoards() {
        document.querySelector(BoardViewportFit.ENEMY_ZONE_SELECTOR)
            ?.classList.remove(BoardViewportFit.COMPACT_CLASS);
        document
            .querySelectorAll(BoardViewportFit.ENEMY_BOARD_SELECTOR)
            .forEach(board => board.classList.remove(BoardViewportFit.OVERLAP_HIDDEN_CLASS));
    }

    collapseEnemyBoards() {
        document
            .querySelectorAll(BoardViewportFit.ENEMY_BOARD_SELECTOR)
            .forEach(board => board.classList.add(BoardViewportFit.OVERLAP_HIDDEN_CLASS));
    }

    smallViewport() {
        return this.viewportHeight() <= BoardViewportFit.SMALL_VIEWPORT_MAX_HEIGHT;
    }

    viewportHeight() {
        const innerHeight = Number(window.innerHeight);
        if (Number.isFinite(innerHeight) && innerHeight > 0) return innerHeight;
        return Number(document.documentElement?.clientHeight) || 0;
    }

    boardsShareShortViewport() {
        const enemyZoneHeight = elementHeight(
            document.querySelector(BoardViewportFit.ENEMY_ZONE_SELECTOR)
        );
        if (enemyZoneHeight <= 0) return false;
        return enemyZoneHeight + this.playerZoneHeight() > this.viewportHeight();
    }

    playerZoneHeight() {
        return BoardViewportFit.PLAYER_ZONE_SELECTORS.reduce(
            (height, selector) => height + elementHeight(document.querySelector(selector)),
            0,
        );
    }
}

function elementHeight(element) {
    const height = element?.getBoundingClientRect?.().height;
    return Number.isFinite(height) ? height : 0;
}

document.addEventListener('DOMContentLoaded', () => {
    const stacking = new LaneCardStacking();
    window.laneCardStacking = stacking;
    window.boardViewportFit = new BoardViewportFit(stacking);
});
