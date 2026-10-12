class LaneCardStacking {
    static OVERFLOW_ROW_CLASS = 'overflow-row';
    static MAX_CARDS_PER_ROW = 15;

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
        const lanes = document.querySelectorAll('.playerBoard .lane');
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

document.addEventListener('DOMContentLoaded', () => {
    window.laneCardStacking = new LaneCardStacking();
});
