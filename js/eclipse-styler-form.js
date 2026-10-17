/** Flat Jade style editor: one Include bar, searchable choices and index actions. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { FLAGS, MODES, resolveSelection } from './eclipse-styler-state.js';

export class StylerForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    render() {
        this.dispose();
        const { root, state } = this.controller, config = state.config;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar');
        const collapsed = state.editor.collapsed === true;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Include');
        const disclosure = button('', 'Include', () => this.controller.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = 'include'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Include:'));
        if (collapsed) {
            const summary = element('span', 'en-panel-summary', Object.entries(FLAGS).filter(([key]) => config[key]).map(([, label]) => label).join(' · ') || 'None');
            summary.title = summary.textContent; disclosure.append(summary);
        }
        bar.append(disclosure);
        if (!collapsed) for (const [key, label] of Object.entries(FLAGS)) {
            const toggle = button(label, label, () => this.controller.edit(state => { state.config[key] = !state.config[key]; }));
            if (key === 'spaces_to_underscores') toggle.title = 'When enabled, replace underscores with spaces in both output prompts. When disabled, leave underscores unchanged.';
            toggle.dataset.field = key; toggle.setAttribute('aria-pressed', String(config[key])); bar.append(toggle);
        }
        content.append(bar);
        const library = element('div', 'en-styler-library');
        const mode = this.menu.field(library, 'Library', MODES[config.style_mode], Object.values(MODES), label => {
            const key = Object.keys(MODES).find(key => MODES[key] === label);
            this.controller.edit(state => state.changeMode(key, this.controller.styles[key]));
        }); mode.dataset.field = 'library';
        const refresh = button('↻', 'Refresh style files', () => this.controller.refresh());
        refresh.disabled = this.controller.loading === true; refresh.dataset.field = 'refresh'; library.append(refresh); content.append(library);
        this.style = this.menu.field(content, 'Style', config.style, this.controller.names(), name => this.controller.edit(state => state.selectStyle(name, this.controller.names())));
        this.style.dataset.field = 'style';
        const openStyle = () => this.menu.open(this.style, 'Style', this.controller.state.config.style, this.controller.names(), name => this.controller.edit(state => state.selectStyle(name, this.controller.names())));
        this.style.onclick = () => this.menu.trigger === this.style ? this.menu.close(true) : openStyle();
        this.style.onkeydown = event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); openStyle(); } };
        const row = element('div', 'en-panel-seed'); row.setAttribute('role', 'group'); row.setAttribute('aria-label', 'Style index controls');
        const label = element('label', '', 'Index'), input = element('input'); input.type = 'text'; input.inputMode = 'numeric'; input.dataset.field = 'index';
        input.value = state.indexInput(this.controller.names()); input.title = '0-based index. -1 random, -2 increment, -3 decrement each queue.';
        input.oninput = () => this.controller.edit(state => state.setIndex(input.value, this.controller.names()), false);
        input.onblur = () => { input.value = this.controller.state.indexInput(this.controller.names()); }; label.append(input); row.append(label); this.input = input;
        for (const [delta, title] of [[-1, 'Previous style'], [1, 'Next style']]) {
            const control = button(delta < 0 ? '−' : '+', title, () => this.controller.edit(state => state.step(delta, this.controller.names())));
            control.className = 'en-panel-step'; control.dataset.field = `index.step.${delta}`; control.disabled = !this.controller.names().length; row.append(control);
        }
        this.random = button('🌑', 'Random style each run', () => this.controller.edit(state => state.setIndex('-1', this.controller.names())));
        this.last = button('🌘', 'Use last queued style', () => this.controller.edit(state => state.useLast(this.controller.styles[state.editor.lastStyle.mode] ?? [])));
        const fixed = button('🌕', 'Choose fixed random style', () => this.controller.edit(state => {
            const selected = resolveSelection({ ...state.config, policy: 'random' }, this.controller.names(), { mode: state.config.style_mode, style: state.config.style });
            state.config.policy = 'fixed'; state.selectStyle(selected.style, this.controller.names());
        })); fixed.disabled = !this.controller.names().length;
        [this.random, this.last, fixed].forEach((control, index) => { control.dataset.field = `index.action.${index}`; row.append(control); }); content.append(row);
        this.status = element('div', 'en-panel-note'); this.status.setAttribute('role', 'status'); content.append(this.status);
        if (this.controller.message) { const note = element('div', 'en-panel-note', this.controller.message); note.setAttribute('role', 'status'); content.append(note); }
        root.replaceChildren(content); this.syncSummaries();
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    syncSummaries() {
        const { config, editor } = this.controller.state, names = this.controller.names(), index = names.indexOf(config.style);
        this.input.setCustomValidity(Number.isInteger(config.index) ? '' : 'Enter a style index or -1, -2, -3.');
        const label = index < 0 ? `${config.style} (unavailable)` : config.style;
        this.style.firstElementChild.textContent = label; this.style.title = label;
        this.status.textContent = `${{ fixed: 'Fixed', random: 'Random each run', increment: 'Increment each run', decrement: 'Decrement each run' }[config.policy]} · ${index < 0 ? 'Style unavailable' : `Index ${index} · ${names.length} styles`}`;
        this.random.disabled = !names.length; this.random.setAttribute('aria-pressed', String(config.policy === 'random'));
        this.last.disabled = !editor.lastStyle;
        this.last.title = editor.lastStyle ? `Use last queued style: ${editor.lastStyle.style}` : 'Use last queued style (queue a prompt first)';
    }
    dispose() { this.menu.close(); }
}
