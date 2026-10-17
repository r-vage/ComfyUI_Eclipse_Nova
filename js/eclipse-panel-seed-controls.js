/** Seed input and compact actions shared by the new Eclipse Nova panels. */
import { element, button } from './eclipse-panel-controls.js';

export function seedControls(parent, controller) {
    const edit = (fn, render = true) => controller.edit(fn, render);
    const row = element('div', 'en-panel-seed'); row.setAttribute('role', 'group'); row.setAttribute('aria-label', 'Seed controls');
    const label = element('label', '', 'Seed'), input = element('input'); input.type = 'text'; input.inputMode = 'numeric';
    input.value = controller.state.seedInput(); input.dataset.field = 'seed';
    input.title = 'Exact seed, -1 for random each run, -2 to increment, -3 to decrement.';
    input.oninput = () => { edit(state => state.setSeed(input.value), false); sync(); };
    label.append(input); row.append(label);
    for (const [delta, title] of [[-1, 'Decrease seed by 1'], [1, 'Increase seed by 1']]) {
        const control = button(delta < 0 ? '−' : '+', title, () => edit(state => state.stepSeed(delta)));
        control.className = 'en-panel-step'; control.dataset.field = `seed.step.${delta}`; row.append(control);
    }
    const random = button('🌑', 'Randomize each run', () => edit(state => state.setSeed('-1')));
    const last = button('🌘', 'Use last queued seed', () => edit(state => { state.config.seed = { ...state.config.seed, value: state.editor.lastSeed, policy: 'fixed' }; }));
    const fixed = button('🌕', 'Create fixed random seed', () => edit(state => { state.config.seed = { ...state.config.seed, value: state.randomSeed(), policy: 'fixed' }; }));
    [random, last, fixed].forEach((control, index) => { control.dataset.field = `seed.action.${index}`; row.append(control); });
    const sync = () => {
        input.setCustomValidity(controller.state.validSeed(controller.state.config.seed.value) ? '' : `Enter a seed from 0 to ${controller.state.maxSeed}, or -1, -2, -3.`);
        random.setAttribute('aria-pressed', String(controller.state.config.seed.policy === 'random'));
        last.disabled = !controller.state.validSeed(controller.state.editor.lastSeed);
        last.title = last.disabled ? 'Use last queued seed (requires a queued seed within the selected range)' : `Use last queued seed: ${controller.state.editor.lastSeed}`;
    };
    sync(); parent.append(row);
}
