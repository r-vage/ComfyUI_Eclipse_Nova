/** Grouped aspect and resolution choices in a zoom-aware browser top-layer menu. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';

function label(target, text, ratio) {
    const value = element('span', 'en-size-choice-value', text);
    if (ratio) {
        const icon = element('span', 'en-size-ratio'); icon.setAttribute('aria-hidden', 'true');
        const shape = element('span'); shape.style.width = `${15 * Math.min(1, ratio[0] / ratio[1])}px`;
        shape.style.height = `${15 * Math.min(1, ratio[1] / ratio[0])}px`; icon.append(shape); value.prepend(icon);
    }
    const caret = element('span', '', '▾'); caret.setAttribute('aria-hidden', 'true'); target.replaceChildren(value, caret);
}

export class SizeMenu extends SearchMenu {
    field(parent, { name, key, value, choices, change, disabled = false, display }) {
        const field = element('div', 'en-panel-field'); field.append(element('span', '', name));
        const selected = display ?? choices.find(choice => choice.value === value) ?? { label: `${value} (unavailable)` };
        const trigger = button('', name, () => this.trigger === trigger ? this.close(true) : this.open(trigger, name, value, choices, change));
        trigger.className = 'en-panel-select'; trigger.dataset.field = key; trigger.disabled = disabled; trigger.title = selected.label;
        trigger.setAttribute('role', 'combobox'); trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-haspopup', 'listbox');
        label(trigger, selected.label, selected.ratio);
        trigger.onkeydown = event => {
            if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); this.open(trigger, name, value, choices, change); }
        };
        field.append(trigger); parent.append(field);
        return { trigger, display: (text, ratio) => { label(trigger, text, ratio); trigger.title = text; } };
    }
    open(trigger, name, value, choices, change) {
        this.close();
        const menu = element('div', 'en-panel-menu en-size-menu'); menu.popover = 'manual';
        menu.id = `en-size-options-${crypto.randomUUID()}`; menu.setAttribute('role', 'listbox'); menu.setAttribute('aria-label', name);
        const groups = new Map(), buttons = [];
        for (const choice of choices) {
            const name = choice.group ?? '';
            if (!groups.has(name)) {
                const group = element('div', 'en-size-column en-panel-results');
                if (name) { group.setAttribute('role', 'group'); group.setAttribute('aria-label', name); group.append(element('div', 'en-size-heading', name)); }
                groups.set(name, group); menu.append(group);
            }
            const option = button('', choice.label, () => { this.close(true); change(choice.value); }); label(option, choice.label, choice.ratio);
            option.tabIndex = -1; option.setAttribute('role', 'option'); option.setAttribute('aria-selected', String(choice.value === value));
            groups.get(name).append(option); buttons.push(option);
        }
        menu.onkeydown = event => {
            event.stopPropagation(); if (event.isComposing) return;
            if (event.key === 'Escape') { event.preventDefault(); this.close(true); return; }
            if (event.key === 'Tab') { this.close(true); return; }
            if (!buttons.length || !['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); const index = buttons.indexOf(document.activeElement);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
                : (index + (['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : -1) + buttons.length) % buttons.length;
            buttons[next].focus({ preventScroll: true }); buttons[next].scrollIntoView({ block: 'nearest' });
        };
        menu.onpointerdown = event => event.stopPropagation();
        menu.addEventListener('wheel', event => event.stopPropagation(), { passive: true });
        document.body.append(menu); menu.showPopover(); this.menu = menu; this.trigger = trigger;
        trigger.setAttribute('aria-expanded', 'true'); trigger.setAttribute('aria-controls', menu.id);
        const rect = trigger.getBoundingClientRect(), scale = rect.width / trigger.offsetWidth || 1;
        menu.style.maxWidth = `${(innerWidth - 16) / scale}px`; menu.style.maxHeight = `${Math.min(340, (innerHeight - 16) / scale)}px`;
        menu.style.transform = `scale(${scale})`;
        const width = menu.offsetWidth * scale, height = menu.offsetHeight * scale;
        menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
        menu.style.top = `${Math.max(8, Math.min(rect.bottom + height + 4 < innerHeight ? rect.bottom + 4 : rect.top - height - 4, innerHeight - height - 8))}px`;
        const current = buttons.find(choice => choice.getAttribute('aria-selected') === 'true') ?? buttons[0];
        current?.focus({ preventScroll: true }); current?.scrollIntoView({ block: 'nearest' });
        this.events = new AbortController(); const signal = this.events.signal;
        document.addEventListener('pointerdown', event => { if (!menu.contains(event.target) && !trigger.contains(event.target)) this.close(); }, { capture: true, signal });
        document.addEventListener('wheel', event => { if (!menu.contains(event.target)) this.close(); }, { capture: true, passive: true, signal });
        window.addEventListener('resize', () => this.close(), { signal });
        this.observer = new MutationObserver(() => this.close());
        for (let parent = trigger.parentElement; parent; parent = parent.parentElement) {
            this.observer.observe(parent, { childList: true, attributes: true, attributeFilter: ['style', 'class'] });
        }
    }
}
