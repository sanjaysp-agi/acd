// Shared buildless-JSX helper: htm bound to React.createElement.
// Vendored globals (no npm, no bundler) -- see web/vendor/.
export const React = window.React;
export const ReactDOM = window.ReactDOM;
export const html = window.htm.bind(React.createElement);
