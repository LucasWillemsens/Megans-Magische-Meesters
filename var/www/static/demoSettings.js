const holdRange = document.getElementById('shortcutHoldRange');
const holdOutput = document.getElementById('shortcutHoldOutput');

if (holdRange && holdOutput) {
    holdRange.addEventListener('input', () => {
        holdOutput.textContent = `${holdRange.value} ms`;
    });
}
