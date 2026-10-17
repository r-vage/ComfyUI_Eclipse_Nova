/** Compact resize controls; only options used by the selected mode are created. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';

export class ResizeForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    choice(parent, key, label) {
        const { state } = this.controller, choices = state.spec.choices[key];
        const trigger = this.menu.field(parent, label, choices[state.config[key]] ?? state.config[key], Object.values(choices), label => {
            this.controller.edit(state => state.change(key, Object.keys(choices).find(key => choices[key] === label)));
        }); trigger.dataset.field = key; return trigger;
    }
    number(parent, key, title) {
        const { state } = this.controller, spec = state.spec.numbers[key];
        const label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.dataset.field = key;
        for (const name of ['min', 'max', 'step']) input[name] = spec[name];
        input.value = state.config[key] ?? ''; input.title = title ?? spec.label;
        input.oninput = () => this.controller.edit(state => { state.config[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', title ?? spec.label), input); parent.append(label);
        return input;
    }
    render() {
        this.dispose();
        const { root, state } = this.controller, config = state.config;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar');
        const collapsed = state.editor.collapsed === true;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Scale to');
        const disclosure = button('', 'Scale to', () => this.controller.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = 'scale'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Scale to:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', `${state.spec.choices.scale_to[config.scale_to]} · ${config.use_input_size ? 'Use inputs' : 'Panel size'}`));
        bar.append(disclosure);
        if (!collapsed) for (const [key, label] of Object.entries(state.spec.choices.scale_to)) {
            const control = button(label, label, () => this.controller.edit(state => state.change('scale_to', key)));
            control.setAttribute('aria-pressed', String(config.scale_to === key)); control.dataset.field = `scale.${key}`; bar.append(control);
        }
        if (!collapsed) {
            const control = button('Use inputs', 'Use inputs', () => this.controller.edit(state => state.change('use_input_size', !state.config.use_input_size)));
            control.dataset.field = 'use_input_size'; control.className = 'en-resize-use-inputs';
            control.title = 'Use connected width/height when non-None. Disable to use the panel size.';
            control.setAttribute('aria-pressed', String(config.use_input_size)); bar.append(control);
        }
        content.append(bar);
        const dimensions = element('div', 'en-panel-grid');
        if (config.scale_to === 'custom') {
            for (const key of ['custom_width', 'custom_height']) this.number(dimensions, key).title = 'Target pixels; 0 keeps the source dimension.';
        } else {
            const labels = { longest: 'Longest side', shortest: 'Shortest side', width: 'Width', height: 'Height', total_pixels: 'Pixels (kpx)' };
            const input = this.number(dimensions, 'size', labels[config.scale_to]);
            if (config.scale_to === 'total_pixels') input.title = 'Thousands of pixels: 1000 = 1 megapixel.';
            this.choice(dimensions, 'aspect_ratio', 'Aspect ratio');
        }
        content.append(dimensions);
        const fitting = element('div', 'en-panel-grid'); this.choice(fitting, 'fit', 'Fit'); this.choice(fitting, 'method', 'Method'); content.append(fitting);
        const padding = element('div', 'en-panel-grid');
        if (Object.hasOwn(config, 'crop_position')) this.choice(padding, 'crop_position', 'Position');
        if (config.fit === 'pad') {
            const label = element('label', 'en-panel-field'), input = element('input');
            input.type = 'color'; input.dataset.field = 'pad_color'; input.title = 'Choose padding color';
            // Native pickers need #RRGGBB; saved configurations also accept #RGB and unprefixed hex.
            const color = String(config.pad_color ?? '').replace(/^#/, '');
            const hex = /^[0-9a-f]{3}$/i.test(color) ? [...color].map(digit => digit + digit).join('') : color;
            input.value = `#${hex}`;
            input.setCustomValidity(/^[0-9a-f]{6}$/i.test(hex) ? '' : 'Select a valid padding color.');
            input.oninput = input.onchange = () => {
                input.setCustomValidity('');
                if (this.controller.state.config.pad_color !== input.value) this.controller.edit(state => { state.config.pad_color = input.value; }, false);
            };
            label.append(element('span', '', 'Padding color'), input); padding.append(label);
        }
        if (padding.childElementCount) content.append(padding);
        const processing = element('div', 'en-panel-grid'); this.number(processing, 'divisible_by'); this.choice(processing, 'device', 'Device'); content.append(processing);
        if (config.fit === 'resize') content.append(element('div', 'en-panel-note', 'Keeps the image ratio; output may be smaller than the target.'));
        if (config.device === 'gpu' && config.method === 'lanczos') content.append(element('div', 'en-panel-note', 'GPU uses Bicubic for Lanczos resampling.'));
        const connected = (this.controller.node.inputs ?? []).filter(input => ['width', 'height'].includes(input.name) && input.link != null).map(input => input.name);
        if (connected.length) {
            const note = element('div', 'en-panel-note', config.use_input_size
                ? `Connected ${connected.join(' / ')} takes priority when non-None. Panel values remain available otherwise.`
                : `Connected ${connected.join(' / ')} is ignored. Using the panel size.`);
            note.setAttribute('role', 'status'); content.append(note);
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    syncSummaries() {}
    dispose() { this.menu.close(); }
}
