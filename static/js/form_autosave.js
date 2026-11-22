(function () {
    'use strict';

    var VERSION = '1';
    var PREFIX = 'maquirent:form-draft:' + VERSION + ':';
    var PENDING_KEY = PREFIX + 'pending';
    var MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
    var saveTimers = new WeakMap();
    var scope = document.body.dataset.formAutosaveScope || 'visitor';

    function warn(error) {
        if (window.console && typeof window.console.warn === 'function') {
            window.console.warn('No se pudo conservar el borrador del formulario.', error);
        }
    }

    function storageGet(storage, key) {
        try {
            var value = storage.getItem(key);
            return value ? JSON.parse(value) : null;
        } catch (error) {
            warn(error);
            return null;
        }
    }

    function storageSet(storage, key, value) {
        try {
            if (value === null) {
                storage.removeItem(key);
            } else {
                storage.setItem(key, JSON.stringify(value));
            }
            return true;
        } catch (error) {
            warn(error);
            return false;
        }
    }

    function formKey(form, index) {
        var identifier = form.id || form.getAttribute('name') || String(index);
        var action = new URL(form.getAttribute('action') || window.location.href, window.location.href);
        return PREFIX + scope + ':' + action.pathname + ':' + form.method.toLowerCase() + ':' + identifier;
    }

    function isSensitive(control) {
        var identity = [
            control.name,
            control.id,
            control.autocomplete
        ].join(' ').toLowerCase();

        return /password|passwd|passphrase|contrasena|contrase[nñ]a|csrf|token|secret|cvv|cvc/.test(identity);
    }

    function isPersistable(form, control) {
        if (!control.name || control.disabled || control.hasAttribute('data-autosave-ignore')) {
            return false;
        }

        var tagName = control.tagName.toLowerCase();
        var type = (control.type || '').toLowerCase();

        if (!['input', 'select', 'textarea'].includes(tagName)) {
            return false;
        }

        if (['button', 'file', 'hidden', 'image', 'reset', 'submit'].includes(type)) {
            return false;
        }

        if (isSensitive(control) || form.hasAttribute('data-autosave-ignore')) {
            return false;
        }

        return true;
    }

    function serialize(form) {
        var controls = Array.prototype.slice.call(form.elements).filter(function (control) {
            return isPersistable(form, control);
        });

        return controls.map(function (control) {
            var value = control.value;

            if (control.tagName.toLowerCase() === 'select' && control.multiple) {
                value = Array.prototype.slice.call(control.options)
                    .filter(function (option) { return option.selected; })
                    .map(function (option) { return option.value; });
            }

            return {
                id: control.id || null,
                name: control.name,
                type: (control.type || control.tagName).toLowerCase(),
                value: value,
                checked: control.type === 'checkbox' || control.type === 'radio'
                    ? control.checked
                    : null
            };
        });
    }

    function hasValues(fields) {
        return fields.some(function (field) {
            if (field.checked !== null) {
                return field.checked;
            }
            return Array.isArray(field.value)
                ? field.value.length > 0
                : field.value !== '' && field.value !== null;
        });
    }

    function save(form, key) {
        var fields = serialize(form);
        if (!fields.length || !hasValues(fields)) {
            storageSet(window.localStorage, key, null);
            return;
        }

        storageSet(window.localStorage, key, {
            fields: fields,
            updatedAt: Date.now()
        });
    }

    function restore(form, key) {
        var draft = storageGet(window.localStorage, key);
        if (!draft || !Array.isArray(draft.fields)) {
            return false;
        }

        if (!draft.updatedAt || Date.now() - draft.updatedAt > MAX_AGE_MS) {
            storageSet(window.localStorage, key, null);
            return false;
        }

        var matched = 0;
        draft.fields.forEach(function (field) {
            var candidates = Array.prototype.slice.call(form.elements).filter(function (control) {
                if (!isPersistable(form, control) || control.name !== field.name) {
                    return false;
                }

                return field.id ? control.id === field.id : true;
            });

            candidates.forEach(function (control) {
                if (control.type === 'radio' || control.type === 'checkbox') {
                    if (control.type === 'radio' && control.value !== field.value) {
                        return;
                    }
                    control.checked = Boolean(field.checked);
                } else if (control.tagName.toLowerCase() === 'select' && control.multiple) {
                    var selectedValues = Array.isArray(field.value) ? field.value : [];
                    Array.prototype.forEach.call(control.options, function (option) {
                        option.selected = selectedValues.includes(option.value);
                    });
                } else {
                    control.value = field.value;
                }

                control.dispatchEvent(new Event('input', { bubbles: true }));
                control.dispatchEvent(new Event('change', { bubbles: true }));
                matched += 1;
            });
        });

        return matched > 0;
    }

    function currentNavigationType() {
        if (!window.performance || !window.performance.getEntriesByType) {
            return 'navigate';
        }

        var entries = window.performance.getEntriesByType('navigation');
        return entries.length ? entries[0].type : 'navigate';
    }

    function hasValidationErrors(form) {
        return Boolean(form.querySelector(
            '.errorlist, .invalid-feedback, .is-invalid, [aria-invalid="true"]'
        ));
    }

    function hasFailureMessage() {
        return Boolean(document.querySelector(
            '.alert-danger, .alert-error, .alert-warning:not([hidden]), ' +
            '[role="alert"][data-level="error"], [role="alert"][data-level="warning"], .errornote'
        ));
    }

    function hasSuccessMessage() {
        return Boolean(document.querySelector(
            '.alert-success, [role="alert"][data-level="success"]'
        ));
    }

    function registerPending(key) {
        var pending = storageGet(window.sessionStorage, PENDING_KEY);
        if (!Array.isArray(pending)) {
            pending = [];
        }
        if (!pending.includes(key)) {
            pending.push(key);
        }
        storageSet(window.sessionStorage, PENDING_KEY, pending);
    }

    function clearCompletedDrafts(formsByKey) {
        var pending = storageGet(window.sessionStorage, PENDING_KEY);
        if (!Array.isArray(pending)) {
            return;
        }

        var remaining = pending.filter(function (key) {
            var form = formsByKey.get(key);

            if (hasFailureMessage() || (form && hasValidationErrors(form))) {
                return true;
            }

            if (form && currentNavigationType() === 'reload' && !hasSuccessMessage()) {
                return true;
            }

            storageSet(window.localStorage, key, null);
            return false;
        });

        storageSet(window.sessionStorage, PENDING_KEY, remaining.length ? remaining : null);
    }

    var formsByKey = new Map();
    var forms = Array.prototype.slice.call(document.querySelectorAll('form')).filter(function (form) {
        var method = form.method.toLowerCase();
        return (method === 'get' || method === 'post') && !form.hasAttribute('data-autosave-ignore');
    });

    forms.forEach(function (form, index) {
        var key = formKey(form, index);
        if (serialize(form).length === 0) {
            return;
        }

        formsByKey.set(key, form);

        function scheduleSave() {
            window.clearTimeout(saveTimers.get(form));
            saveTimers.set(form, window.setTimeout(function () {
                save(form, key);
            }, 200));
        }

        form.addEventListener('input', scheduleSave);
        form.addEventListener('change', scheduleSave);
        form.addEventListener('reset', function () {
            window.setTimeout(function () {
                storageSet(window.localStorage, key, null);
            }, 0);
        });
        form.addEventListener('submit', function () {
            save(form, key);
            registerPending(key);
        });
    });

    clearCompletedDrafts(formsByKey);
    formsByKey.forEach(function (form, key) {
        restore(form, key);
    });

    window.addEventListener('pagehide', function () {
        formsByKey.forEach(function (form, key) {
            save(form, key);
        });
    });
})();
