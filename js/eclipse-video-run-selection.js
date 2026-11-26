/** Saved-run choices shared by the loader and prompt editor. */
export const NO_RUN = 'None';

export function isSavedRun(value) {
    return typeof value === 'string' && value !== '' && value !== NO_RUN && value !== '(no saved runs found)';
}

export function savedRunOptions(paths) {
    return [NO_RUN, ...paths.filter(isSavedRun)];
}
