(() => {
    'use strict';

    const VERSION = '2';
    const PREFIX = `maquirent:form-draft:${VERSION}:`;
    const LEGACY_PREFIX = 'maquirent:form-draft:1:';
    const saveTimers = new WeakMap();
    const scope = document.body.dataset.formAutosaveScope || 'visitor';
    const session = window.sessionStorage;
    let discardOnPageHide = false;

    function warn(error) {
        console.warn('No se pudo conservar el borrador del formulario.', error);
    }

    function storageGet(key, fallback = null) {
        try {
            const value = session.getItem(key);
            return value ? JSON.parse(value) : fallback;
        } catch (error) {
            warn(error);
            return fallback;
        }
    }

    function storageSet(key, value) {
        try {
            if (value === null) {
                session.removeItem(key);
            } else {
                session.setItem(key, JSON.stringify(value));
            }
        } catch (error) {
            warn(error);
        }
    }

    function storageKeys() {
        const keys = [];
        for (let index = 0; index < session.length; index += 1) {
            const key = session.key(index);
            if (key && (key.startsWith(PREFIX) || key.startsWith(LEGACY_PREFIX))) {
                keys.push(key);
            }
        }
        return keys;
    }

    function clearAllDrafts() {
        storageKeys().forEach((key) => session.removeItem(key));
    }

    function clearLegacyDrafts() {
        try {
            const keys = [];
            for (let index = 0; index < window.localStorage.length; index += 1) {
                const key = window.localStorage.key(index);
                if (key && key.startsWith(LEGACY_PREFIX)) keys.push(key);
            }
            keys.forEach((key) => window.localStorage.removeItem(key));
        } catch (error) {
            warn(error);
        }
    }

    function pageIdentity() {
        return `${window.location.pathname}${window.location.search}`;
    }

    function formKey(form, index) {
        const identifier = form.id || form.getAttribute('name') || String(index);
        const action = new URL(form.getAttribute('action') || window.location.href, window.location.href);
        return `${PREFIX}${scope}:${pageIdentity()}:${action.pathname}:${form.method.toLowerCase()}:${identifier}`;
    }

    function isSensitive(control) {
        const identity = [control.name, control.id, control.autocomplete]
            .join(' ')
            .toLowerCase();
        return /password|passwd|passphrase|contrasena|contrase[nñ]a|csrf|token|secret|cvv|cvc/.test(identity);
    }

    function isPersistable(form, control) {
        if (!control.name || control.disabled || control.hasAttribute('data-autosave-ignore')) {
            return false;
        }

        const tagName = control.tagName.toLowerCase();
        const type = (control.type || '').toLowerCase();
        if (!['input', 'select', 'textarea'].includes(tagName)) return false;
        if (['button', 'file', 'hidden', 'image', 'reset', 'submit'].includes(type)) return false;
        return !isSensitive(control) && !form.hasAttribute('data-autosave-ignore');
    }

    function serialize(form) {
        return Array.from(form.elements)
            .filter((control) => isPersistable(form, control))
            .map((control) => {
                let value = control.value;
                if (control.tagName.toLowerCase() === 'select' && control.multiple) {
                    value = Array.from(control.options)
                        .filter((option) => option.selected)
                        .map((option) => option.value);
                }

                return {
                    id: control.id || null,
                    name: control.name,
                    value,
                    checked: control.type === 'checkbox' || control.type === 'radio'
                        ? control.checked
                        : null,
                };
            });
    }

    function hasValues(fields) {
        return fields.some((field) => {
            if (field.checked !== null) return field.checked;
            return Array.isArray(field.value)
                ? field.value.length > 0
                : field.value !== '' && field.value !== null;
        });
    }

    function save(form, key) {
        const fields = serialize(form);
        if (!fields.length || !hasValues(fields)) {
            storageSet(key, null);
            return;
        }

        storageSet(key, {
            page: pageIdentity(),
            fields,
            updatedAt: Date.now(),
        });
    }

    function clearDraft(key) {
        storageSet(key, null);
    }

    function restore(form, key) {
        const draft = storageGet(key);
        if (!draft || !Array.isArray(draft.fields) || draft.page !== pageIdentity()) {
            return;
        }

        draft.fields.forEach((field) => {
            Array.from(form.elements)
                .filter((control) => isPersistable(form, control)
                    && control.name === field.name
                    && (!field.id || control.id === field.id))
                .forEach((control) => {
                    if (control.type === 'radio' || control.type === 'checkbox') {
                        if (control.type === 'radio' && control.value !== field.value) return;
                        control.checked = Boolean(field.checked);
                    } else if (control.tagName.toLowerCase() === 'select' && control.multiple) {
                        const selectedValues = Array.isArray(field.value) ? field.value : [];
                        Array.from(control.options).forEach((option) => {
                            option.selected = selectedValues.includes(option.value);
                        });
                    } else {
                        control.value = field.value;
                    }
                    control.dispatchEvent(new Event('input', { bubbles: true }));
                    control.dispatchEvent(new Event('change', { bubbles: true }));
                });
        });
    }

    function navigationType() {
        const entries = window.performance?.getEntriesByType?.('navigation') || [];
        return entries[0]?.type || 'navigate';
    }

    function discardDrafts() {
        discardOnPageHide = true;
        formsByKey.forEach((form) => clearTimeout(saveTimers.get(form)));
        clearAllDrafts();
    }

    clearLegacyDrafts();

    const formsByKey = new Map();
    const forms = Array.from(document.querySelectorAll('form')).filter((form) => {
        const method = form.method.toLowerCase();
        return ['get', 'post'].includes(method) && !form.hasAttribute('data-autosave-ignore');
    });

    forms.forEach((form, index) => {
        const key = formKey(form, index);
        if (serialize(form).length === 0) return;

        formsByKey.set(key, form);
        const scheduleSave = () => {
            clearTimeout(saveTimers.get(form));
            saveTimers.set(form, setTimeout(() => save(form, key), 200));
        };

        form.addEventListener('input', scheduleSave);
        form.addEventListener('change', scheduleSave);
        form.addEventListener('reset', () => setTimeout(() => clearDraft(key), 0));
    });

    if (navigationType() === 'reload') {
        formsByKey.forEach((form, key) => restore(form, key));
    } else {
        clearAllDrafts();
    }

    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!link
            || event.button !== 0
            || event.ctrlKey
            || event.metaKey
            || event.shiftKey
            || event.altKey
            || event.defaultPrevented
            || link.target === '_blank'
            || link.hasAttribute('download')) {
            return;
        }
        const destination = new URL(link.href, window.location.href);
        const changesDocument = destination.origin !== window.location.origin
            || destination.pathname !== window.location.pathname
            || destination.search !== window.location.search;
        if (changesDocument) {
            queueMicrotask(() => {
                if (!event.defaultPrevented) discardDrafts();
            });
        }
    });

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (form instanceof HTMLFormElement) {
            queueMicrotask(() => {
                if (!event.defaultPrevented) discardOnPageHide = true;
            });
        }
    }, true);

    window.addEventListener('pagehide', () => {
        if (discardOnPageHide) {
            clearAllDrafts();
        } else {
            formsByKey.forEach((form, key) => save(form, key));
        }
    });

    window.addEventListener('pageshow', (event) => {
        if (!event.persisted) return;
        discardDrafts();
        formsByKey.forEach((form) => form.reset());
    });
})();
