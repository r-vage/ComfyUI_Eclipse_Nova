/** Smart Prompt uses the shared structured-panel seed queue handling. */
import { NODE_ID, EDITOR_KEY } from './eclipse-smart-prompt-state.js';
import { installSeedQueueHook } from './eclipse-panel-seed-queue.js';

export function installPromptQueueHook(api, app, controllers, random) {
    return installSeedQueueHook(api, app, controllers, { nodeId: NODE_ID, editorKey: EDITOR_KEY }, random);
}
