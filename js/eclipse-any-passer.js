import {
    app
} from './comfy/index.js';
import {
    setupAnyTypeHandling
} from './eclipse-any-type-handler.js';
app.registerExtension({
    name: 'EclipseNova.RouterAnyPasser',
    async beforeRegisterNodeDef(e, n, p) {
        if ('Any Passer [Eclipse Nova]' === n.name) {
            const n = e.prototype.onNodeCreated;
            e.prototype.onNodeCreated = function () {
                (n && n.apply(this, arguments), setupAnyTypeHandling(this, 0, 0));
            };
        }
    },
});
