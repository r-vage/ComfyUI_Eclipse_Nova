/** Optional theme selection linking through installed packs' public settings. */
export function createThemeLink({ app, api, notice }) {
    const settingId = 'EclipseNova.NodeDesign.LinkNovaThemes';
    const companions = [
        { id: 'SML2.NodeDesign', name: 'Smart Model Loader Nova' },
        { id: 'SmartLLMNova.NodeDesign', name: 'SmartLLM Nova' },
    ];
    const settings = app.ui.settings;
    let enabled = false, started = false, theme = null, revision = 0, saving = 0;
    let pending = Promise.resolve(), button = null;
    const installed = () => companions.filter(({ id }) => settings.settingsLookup?.[id]);

    function paint() {
        if (!button) return;
        button.textContent = enabled ? 'Unlink themes' : 'Link themes';
        button.setAttribute('aria-pressed', String(enabled));
        button.disabled = !started || saving > 0 || (!enabled && !installed().length);
        button.title = !installed().length
            ? 'Enable SmartLLM Nova or Smart Model Loader Nova to link its theme.'
            : 'Keep the installed Nova packs on the theme selected in Eclipse.';
    }

    async function sync(request) {
        if (!enabled || !started || !theme || request !== revision) return;
        const selected = theme, errors = [];
        for (const { id, name } of installed()) {
            if (!enabled || request !== revision) break;
            const choices = settings.settingsLookup[id].options;
            const available = Array.isArray(choices) && choices.some(option =>
                (typeof option === 'string' ? option : option.value) === selected
                && !(typeof option === 'object' && option.text?.startsWith('Unavailable:')));
            if (!available) {
                errors.push(`${name} does not have theme “${selected}”. Add it to that pack’s themes folder and reload its themes.`);
                continue;
            }
            if (settings.getSettingValue(id) === selected) continue;
            try {
                // The owning pack validates, applies and saves its own preference.
                await settings.setSettingValueAsync(id, selected);
                if (settings.getSettingValue(id) !== selected) throw Error('The theme change did not save.');
            } catch (error) {
                errors.push(`${name} could not select “${selected}”: ${error.message}`);
            }
        }
        if (errors.length && request === revision) notice(errors.join('\n'));
    }

    function setTheme(value) {
        theme = value;
        const request = ++revision;
        pending = pending.then(() => sync(request)).catch(error => notice(`Could not link Nova themes: ${error.message}`));
        return pending;
    }

    function setEnabled(value) {
        if (typeof value !== 'boolean') return Promise.resolve();
        const request = ++revision;
        saving++; paint();
        pending = pending.then(async () => {
            try {
                if (value && !installed().length) {
                    notice('No installed SmartLLM Nova or Smart Model Loader Nova theme control is available.');
                    return;
                }
                if (value !== enabled) {
                    const response = await api.fetchApi('/eclipse-nova/config/update', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ link_nova_themes: value }),
                    });
                    const result = await response.json();
                    if (!response.ok || !result.success) throw Error(result.error || 'Could not save the theme link.');
                    enabled = value;
                }
                await sync(request);
            } catch (error) {
                notice(`Could not change the Nova theme link: ${error.message}`);
            } finally { saving--; paint(); }
        });
        return pending;
    }

    function initialize(config = {}) {
        enabled = config.link_nova_themes === true;
        settings.addSetting({
            id: settingId, category: ['Eclipse Nova', 'Appearance', 'LinkNovaThemes'],
            name: 'Link Nova themes', defaultValue: '', sortOrder: 499.5,
            tooltip: 'Keep SmartLLM Nova and Smart Model Loader Nova on Eclipse’s selected theme. Click again to unlink. Custom themes must exist in each linked pack.',
            type() {
                button = document.createElement('button');
                button.className = 'comfy-menu-btn'; button.type = 'button';
                button.onclick = () => setEnabled(!enabled);
                paint();
                return button;
            },
        });
    }

    function start() {
        // ComfyUI runs setup after every pack's asynchronous init has finished.
        started = true; paint();
        return setTheme(theme);
    }

    return { initialize, start, setTheme, setEnabled };
}
