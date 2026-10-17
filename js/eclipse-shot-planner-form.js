/** SPDX-License-Identifier: Apache-2.0
 * Shared panel sections for manual lists, planner filters and project history.
 */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';

export class ShotPlannerForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); this.textSizes = new TextFieldSizes(controller); }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    get params() { return this.config.parameters; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.dispose();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content);
        this.section(content, 'batch', 'Batch', parent => {
            const grid = this.grid(parent);
            this.textInput(grid, 'project', 'Project', 200); this.textInput(grid, 'batch_id', 'Batch ID', 80);
            this.number(grid, 'count'); if (this.config.mode === 'Manual') this.number(grid, 'manual_start');
            if (this.controller.connected('project')) this.note(parent, 'Connected project takes priority. The local project name is retained for an unconnected or None input.');
            const status = element('div', 'en-panel-note'); status.dataset.planStatus = ''; parent.append(status); this.syncStatus(status);
        });
        for (const key of ['character_lock', 'outfit_lock', 'scene']) this.section(content, key, this.state.spec.texts[key][0], parent => this.textarea(parent, key));
        if (this.config.mode === 'Manual') this.section(content, 'manual_shots', 'Manual shots', parent => {
            this.textarea(parent, 'manual_shots', 6);
            this.note(parent, 'One shot per nonempty line, in order, including duplicates. Character, Outfit and Scene are added to each shot. Manual never reads or saves reservations.');
        });
        else {
            this.section(content, 'planning', 'Planning', parent => {
                const grid = this.grid(parent);
                this.choice(grid, 'body_mode', 'Posture'); this.choice(grid, 'pose_category', 'Pose category');
                this.choice(grid, 'selection', 'Output distance');
                const control = this.menu.field(grid, 'Expression', this.params.expression,
                    this.controller.expressions ?? this.state.spec.expressions, value => this.edit(state => { state.config.parameters.expression = value; }));
                control.dataset.field = 'parameters.expression'; control.title = this.state.spec.tips.expression;
                this.choice(parent, 'stop_when', 'Stop when');
                this.textarea(parent, 'choices', 2);
            });
            this.section(content, 'history', 'History & files', parent => {
                this.note(parent, 'Cooldowns count previously selected shots:');
                const grid = this.grid(parent);
                this.number(grid, 'pose_cooldown');
                if (this.params.expression === 'random') this.number(grid, 'expression_cooldown');
                this.number(grid, 'camera_cooldown');
                this.note(parent, this.params.operation === 'reserve'
                    ? 'Reserve saves all three candidates before generation. Unchanged batch settings replay them; changed settings create a numbered variant. Generation failure does not release reservations.'
                    : 'Preview uses current files and empty history, saves nothing and still allows downstream generation.');
                const actions = element('div', 'en-panel-inline');
                const reload = button('↻ Reload files', 'Reload planner files', () => this.controller.reloadFiles());
                reload.disabled = !!this.controller.reloading; actions.append(reload);
                const reset = button('Reset reservations…', 'Reset reservations', () => this.controller.resetReservations());
                reset.disabled = !!this.controller.resetting; actions.append(reset); parent.append(actions);
                this.note(parent, 'Edit camera.json, poses.json, expressions.json and rules.json in prompts/shot_planner. Reloading updates options; saved batches keep their snapshots. Reset clears all batches for the confirmed project.');
                const status = element('div', 'en-panel-note', this.controller.status ?? ''); status.setAttribute('role', 'status'); parent.append(status);
            });
        }
        if (this.config.seed.source === 'local') this.section(content, 'seed', 'Seed', parent => {
            seedControls(parent, this.controller);
            this.note(parent, 'Controls planning and derives a generation seed for each shot. Use the seeds output for the dataset sampler. Keep the seed fixed to retry the same reserved batch.');
        });
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const toggle = button('', 'Mode', () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = 'mode'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        const local = this.config.seed.source === 'local';
        if (collapsed) toggle.append(element('span', 'en-panel-summary', `${this.config.mode} · ${this.config.mode === 'Manual' || this.params.operation === 'preview' ? 'Preview' : 'Reserve'} · ${local ? 'Local seed' : 'Input seed'}`));
        bar.append(toggle);
        if (!collapsed) {
            for (const mode of ['Planner', 'Manual']) {
                const control = button(mode, mode, () => this.edit(state => { state.config.mode = mode; }));
                control.dataset.field = `mode.${mode}`; control.setAttribute('aria-pressed', String(this.config.mode === mode)); bar.append(control);
            }
            if (this.config.mode === 'Planner') {
                const control = button('Reserve', 'Reserve', () => this.edit(state => {
                    state.config.parameters.operation = state.config.parameters.operation === 'reserve' ? 'preview' : 'reserve';
                }));
                control.title = 'Enabled: reserve candidates in project history. Disabled: preview from empty history without saving. Both can generate images.';
                control.dataset.field = 'parameters.operation'; control.setAttribute('aria-pressed', String(this.params.operation === 'reserve')); bar.append(control);
            }
            const control = button('Local seed', 'Local seed', () => this.edit(state => state.setLocalSeed(!local, this.controller.connected('seed_input'))));
            control.disabled = local && !this.controller.connected('seed_input'); control.dataset.field = 'seed.source';
            control.setAttribute('aria-pressed', String(local));
            control.title = control.disabled ? 'Connect seed_input to use a shared planner seed.' : local ? 'Local seed is active; the seed input is ignored.' : 'Connected seed is active. Enable to use local seed controls instead.';
            bar.append(control);
        }
        parent.append(bar);
    }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key)); summary.title = summary.textContent; summary.dataset.sectionSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key)));
        pin.dataset.field = `pin.${key}`; pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    grid(parent) { const grid = element('div', 'en-panel-grid'); parent.append(grid); return grid; }
    note(parent, text) { parent.append(element('div', 'en-panel-note', text)); }
    number(parent, key) {
        const field = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = this.params[key] ?? ''; input.dataset.field = `parameters.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = field[name]; input.title = this.state.spec.tips[key] ?? field.label;
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label), input); parent.append(label);
    }
    textInput(parent, key, title, maximum) {
        const label = element('label', 'en-panel-field'), input = element('input'); input.type = 'text';
        input.value = this.params[key]; input.maxLength = maximum; input.dataset.field = `parameters.${key}`; input.title = this.state.spec.tips[key];
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false);
        label.append(element('span', '', title), input); parent.append(label);
    }
    textarea(parent, key, rows = 3) {
        const label = element('label', 'en-panel-field'), input = element('textarea');
        input.rows = rows; input.maxLength = key === 'manual_shots' ? this.state.spec.maxManual : this.state.spec.maxText;
        input.value = this.config.texts[key]; input.title = this.state.spec.tips[key];
        this.textSizes.attach(input, `texts.${key}`);
        input.oninput = () => this.edit(state => { state.config.texts[key] = input.value; }, false);
        label.append(element('span', '', this.state.spec.texts[key][0]), input); parent.append(label);
        if (this.controller.connected(key)) this.note(parent, 'Connected text takes priority when non-None. Edit the source node to change its value; this local text is retained.');
    }
    choice(parent, key, title) {
        const choices = this.state.spec.choices[key], current = this.params[key];
        const control = this.menu.field(parent, title, choices[current] ?? current, Object.values(choices), label => {
            this.edit(state => { state.config.parameters[key] = Object.keys(choices).find(key => choices[key] === label); });
        }); control.dataset.field = `parameters.${key}`; control.title = this.state.spec.tips[key];
    }
    summary(key) {
        if (key === 'batch') return `${this.controller.connected('project') ? 'Input project' : this.params.project} · ${this.params.batch_id} · ${this.params.count} shots`;
        if (key === 'planning') return `${this.params.body_mode} · ${this.params.pose_category} · ${this.params.selection} · ${this.params.expression}`;
        if (key === 'history') return this.params.operation === 'reserve' ? 'Reserve' : 'Preview · no history';
        if (key === 'seed') return this.config.seed.policy === 'fixed' ? this.config.seed.value : `${this.config.seed.policy} each run`;
        if (this.controller.connected(key)) return 'Connected input';
        if (key === 'manual_shots') return `${this.config.texts.manual_shots.split(/\r?\n/).filter(line => line.trim()).length} entries`;
        return this.config.texts[key].trim() ? 'Local text' : 'Empty';
    }
    syncStatus(item) {
        const last = this.state.editor.lastPlan;
        item.textContent = last ? `Last plan: ${last.count} shots · ${last.mode} · ${last.project} / ${last.batch} · ${last.operation}` : '';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
        for (const item of this.controller.root.querySelectorAll('[data-plan-status]')) this.syncStatus(item);
    }
    dispose() { this.menu.close(); this.textSizes.disconnect(); }
}
