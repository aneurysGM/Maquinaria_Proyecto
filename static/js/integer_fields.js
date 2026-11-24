(() => {
    const selector = '[data-integer-input]';

    const formatInteger = (input) => {
        const position = input.selectionStart;
        const original = input.value;
        const digits = original.split('.')[0].replace(/\D/g, '');
        const formatted = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        if (formatted === original) return;

        input.value = formatted;
        if (position !== null && document.activeElement === input) {
            const digitsBeforeCursor = original.slice(0, position).replace(/\D/g, '').length;
            let nextPosition = 0;
            let seenDigits = 0;
            while (nextPosition < formatted.length && seenDigits < digitsBeforeCursor) {
                if (/\d/.test(formatted[nextPosition])) seenDigits += 1;
                nextPosition += 1;
            }
            input.setSelectionRange(nextPosition, nextPosition);
        }
    };

    const prepareInput = (input) => {
        input.type = 'text';
        input.setAttribute('inputmode', 'numeric');
        formatInteger(input);
    };

    document.querySelectorAll(selector).forEach(prepareInput);

    document.addEventListener('input', (event) => {
        if (event.target.matches(selector)) formatInteger(event.target);
    });

    document.addEventListener('submit', (event) => {
        event.target.querySelectorAll(selector).forEach((input) => {
            input.value = input.value.replace(/,/g, '');
        });
    }, true);

    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (!(node instanceof Element)) return;
                if (node.matches(selector)) prepareInput(node);
                node.querySelectorAll(selector).forEach(prepareInput);
            });
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
