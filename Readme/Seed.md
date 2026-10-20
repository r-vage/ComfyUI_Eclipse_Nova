# Seed and Dual Seed

Both nodes are in **🌒 Eclipse Nova / Primitives** and work in classic canvas and Nodes 2.0.

**Seed** has one seed control and output. **Dual Seed_v2** has two independent controls and integer outputs: **Image** and **Prompt**. Connect Image to your sampler and Prompt to the prompt generator's seed input. The existing Seed node remains available.

The shared **64-bit** toggle defaults to enabled. Turning it off selects unsigned 32-bit values for both Dual Seed controls, retaining the lower 32 bits of each value. Values are stored as decimal strings so full 64-bit precision survives editing and workflow saves.

Each row provides exact entry, −/+, randomize each run, use last queued seed and create fixed random seed. Enter `-1` for random, `-2` for increment or `-3` for decrement. Image and Prompt policies are independent. Accepted queues advance increment/decrement values; failed submissions and workflow exports do not. A partial execution advances the node only when that branch needs it. When Dual Seed executes, both outputs are resolved together.

**Results** keeps up to 50 recent unique values in Seed and 50 recent unique Image/Prompt pairs in Dual Seed, newest first. Reusing a pair restores both values as fixed seeds; a 64-bit history entry re-enables 64-bit mode when needed. Results can be collapsed or cleared, and are saved with the workflow. Cached executions also populate the history.
