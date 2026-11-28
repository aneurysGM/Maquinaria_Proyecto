(() => {
    'use strict';

    const VERSION = '3';
    const ROOT = 'maquirent:form-draft:';
    const PREFIX = `${ROOT}${VERSION}:`;
    const SENSITIVE = /password|passwd|passphrase|contrasena|contrase[nñ]a|clave|csrf|xsrf|token|secret|cvv|cvc/;

    const formsByKey = new Map();
    const scope = document.body.dataset.formAutosaveScope || 'visitor';
    // true = el usuario se está yendo (enlace, envío, logout): no se guarda nada.
    let leaving = false;

    function warn(error) {
        console.warn('No se pudo conservar el borrador del formulario.', error);
    }

    function getStorage(name) {
        try {
            return window[name];
        } catch (error) {
            warn(error);
            return null;
        }
    }

    const session = getStorage('sessionStorage');
    if (!session) return;

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

    // Borra todas las claves del autoguardado (de cualquier versión), salvo las de `keep`.
    function removeOwnKeys(storage, keep) {
        if (!storage) return;
        try {
            const keys = [];
            for (let index = 0; index < storage.length; index += 1) {
                const key = storage.key(index);
                if (key && key.startsWith(ROOT) && !(keep && keep.has(key))) keys.push(key);
            }
            keys.forEach((key) => storage.removeItem(key));
        } catch (error) {
            warn(error);
        }
    }

    function clearAllDrafts(keep) {
        removeOwnKeys(session, keep);
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
        if ((control.type || '').toLowerCase() === 'password') return true;
        const identity = [control.name, control.id, control.autocomplete]
            .join(' ')
            .toLowerCase();
        return SENSITIVE.test(identity);
    }

    function isPersistable(form, control) {
        if (
            !control.name
            || control.disabled
            || control.hasAttribute('data-autosave-ignore')
            || control.hasAttribute('data-autosave-keep-initial')
        ) {
            return false;
        }

        const tagName = control.tagName.toLowerCase();
        const type = (control.type || '').toLowerCase();
        if (!['input', 'select', 'textarea'].includes(tagName)) return false;
        if (['button', 'file', 'hidden', 'image', 'reset', 'submit'].includes(type)) return false;
        return !isSensitive(control) && !form.hasAttribute('data-autosave-ignore');
    }

    // true si el usuario cambió el campo respecto al valor con el que cargó la página.
    function isDirty(control) {
        const tagName = control.tagName.toLowerCase();
        const type = (control.type || '').toLowerCase();

        if (type === 'checkbox' || type === 'radio') {
            return control.checked !== control.defaultChecked;
        }

        if (tagName === 'select') {
            const options = Array.from(control.options);
            if (!options.length) return false;
            if (control.multiple) {
                return options.some((option) => option.selected !== option.defaultSelected);
            }
            let initial = options.findIndex((option) => option.defaultSelected);
            if (initial < 0 && control.size <= 1) {
                initial = options.findIndex((option) => !option.disabled);
            }
            return control.selectedIndex !== initial;
        }

        if (type === 'range' || type === 'color') return false;
        return control.value !== control.defaultValue;
    }

    function serialize(form) {
        const controls = Array.from(form.elements).filter((control) => isPersistable(form, control));
        const fields = controls.map((control) => {
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

        return { fields, dirty: controls.some((control) => isDirty(control)) };
    }

    // La marca solo se crea desde pagehide; así, los borradores intermedios nunca se restauran.
    function save(form, key, unloading = false) {
        const { fields, dirty } = serialize(form);
        if (!fields.length || !dirty) {
            storageSet(key, null);
            return;
        }

        storageSet(key, {
            page: pageIdentity(),
            fields,
            unloadSnapshot: unloading,
        });
    }

    function restore(form, key) {
        const draft = storageGet(key);
        if (!draft || !Array.isArray(draft.fields) || draft.page !== pageIdentity()) {
            return;
        }
        if (!draft.unloadSnapshot) {
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

    // El usuario se va (o ya terminó): borra todo y no vuelve a guardar hasta que escriba otra vez.
    function clearControls(form) {
        if (form.hasAttribute('data-autosave-reset-initial')) {
            HTMLFormElement.prototype.reset.call(form);
            Array.from(form.elements).forEach((control) => {
                if (isPersistable(form, control)) {
                    control.dispatchEvent(new Event('input', { bubbles: true }));
                    control.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
            return;
        }

        const restoredDefaults = [];
        Array.from(form.elements).forEach((control) => {
            if (!isPersistable(form, control)) return;

            if (control.hasAttribute('data-autosave-reset-value')) {
                control.value = control.getAttribute('data-autosave-reset-value');
                restoredDefaults.push(control);
                return;
            } else if (control.hasAttribute('data-autosave-reset-selected')) {
                const options = Array.from(control.options);
                let initial = options.findIndex((option) => option.defaultSelected);
                if (initial < 0) initial = options.findIndex((option) => !option.disabled);
                control.selectedIndex = initial;
                restoredDefaults.push(control);
                return;
            } else if (control.type === 'checkbox' || control.type === 'radio') {
                control.checked = false;
            } else if (control.tagName.toLowerCase() === 'select' && control.multiple) {
                Array.from(control.options).forEach((option) => {
                    option.selected = false;
                });
            } else if (control.tagName.toLowerCase() === 'select') {
                control.selectedIndex = -1;
            } else {
                control.value = '';
            }
            control.defaultValue = '';
            control.defaultChecked = false;
        });
        restoredDefaults.forEach((control) => {
            control.dispatchEvent(new Event('input', { bubbles: true }));
            control.dispatchEvent(new Event('change', { bubbles: true }));
        });
    }

    function discardDrafts(clearFields = false) {
        leaving = true;
        clearAllDrafts();
        if (clearFields) {
            formsByKey.forEach(clearControls);
        }
    }

    function resetForms() {
        formsByKey.forEach(clearControls);
        clearAllDrafts();
        leaving = false;
    }

    function hasServerErrors(form) {
        return Boolean(form.querySelector(
            '.is-invalid, .invalid-feedback, [aria-invalid="true"]'
        ));
    }

    function resetCleanForms() {
        formsByKey.forEach((form) => {
            if (!hasServerErrors(form) && !form.hasAttribute('data-preserve-values')) {
                clearControls(form);
            }
        });
        clearAllDrafts();
        leaving = false;
    }

    function disableNativeRestore(form) {
        form.setAttribute('autocomplete', 'off');
        Array.from(form.elements).forEach((control) => {
            if (['input', 'select', 'textarea'].includes(control.tagName.toLowerCase())) {
                control.setAttribute('autocomplete', 'off');
            }
        });
    }

    // Borrador antiguo de localStorage (versiones anteriores).
    removeOwnKeys(getStorage('localStorage'));

    const forms = Array.from(document.querySelectorAll('form')).filter((form) => {
        const method = form.method.toLowerCase();
        return ['get', 'post'].includes(method) && !form.hasAttribute('data-autosave-ignore');
    });

    forms.forEach((form, index) => {
        const key = formKey(form, index);
        if (serialize(form).fields.length === 0) return;

        formsByKey.set(key, form);
        disableNativeRestore(form);

        form.addEventListener('reset', () => setTimeout(() => storageSet(key, null), 0));
    });

    // 1) Solo una recarga (F5) puede devolver los datos. Cualquier otra carga los borra.
    if (navigationType() === 'reload') {
        formsByKey.forEach((form, key) => restore(form, key));
        clearAllDrafts(new Set(formsByKey.keys()));
    } else {
        clearAllDrafts();
    }

    // 2) Cambiar de página / entrar a otro apartado del menú / cerrar sesión por enlace.
    document.addEventListener('click', (event) => {
        if (event.button !== 0
            || event.ctrlKey
            || event.metaKey
            || event.shiftKey
            || event.altKey
            || !(event.target instanceof Element)) {
            return;
        }

        const link = event.target.closest('a[href]');
        if (!link
            || (link.target && link.target !== '_self')
            || link.hasAttribute('download')
            || link.getAttribute('href').startsWith('#')) {
            return;
        }

        const destination = new URL(link.href, window.location.href);
        if (!/^https?:$/.test(destination.protocol)) return;

        const onlyHashChange = destination.origin === window.location.origin
            && destination.pathname === window.location.pathname
            && destination.search === window.location.search
            && destination.hash !== '';

        // Incluye enlaces a la misma URL: es "entrar de nuevo", no una recarga.
        if (!onlyHashChange) {
            queueMicrotask(() => {
                if (!event.defaultPrevented) discardDrafts(true);
            });
        }
    });

    // 3) Guardar / enviar cualquier formulario (también el de cerrar sesión).
    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;

        queueMicrotask(() => {
            if (!event.defaultPrevented) discardDrafts();
        });
    });

    window.addEventListener('pagehide', () => {
        if (leaving) {
            clearAllDrafts();
        } else {
            formsByKey.forEach((form, key) => save(form, key, true));
        }
    });

    // Limpiar también la restauración nativa al entrar de forma normal, volver atrás
    // o recuperar la vista desde la caché. Solo reload usa el borrador propio.
    window.addEventListener('pageshow', (event) => {
        const type = navigationType();
        if (!event.persisted && type === 'reload') {
            formsByKey.forEach((form, key) => restore(form, key));
            clearAllDrafts(new Set(formsByKey.keys()));
            return;
        }
        if (event.persisted || type === 'back_forward') {
            resetForms();
            return;
        }
        // Se borran los formularios nuevos; los de edición restauran los valores iniciales.
        resetCleanForms();
    });

    // Para envíos por AJAX o logout hecho con JavaScript: window.FormAutosave.clear()
    window.FormAutosave = { clear: discardDrafts };
})();