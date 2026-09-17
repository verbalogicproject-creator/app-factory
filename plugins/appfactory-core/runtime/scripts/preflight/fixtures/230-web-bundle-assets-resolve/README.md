# 230-web-bundle-assets-resolve

The white screen: the page loads, every build step is green, and an asset it references
is not where the WebView mount looks for it.

- `bug/` — `index.html` references a hashed script the bundle does not contain (a stale copy).
- `bug-vite-base/` — built with Vite `base: '/myapp/'`; the mount serves the bundle at `/`.
- `bug-css-url/` — HTML is fine; a stylesheet's `url()` names an image that was never emitted.
- `bug-relative-css-font/` — a relative `url()` resolves against the CSS file, not the page:
  `assets/css/site.css` asking for `fonts/inter.woff2` needs `assets/css/fonts/`, and the font sits at `fonts/`.
- `fixed/` — absolute, `./`-relative, CSS-relative, `srcset`, external, `data:` and commented-out
  references; an `<a href>` is navigation, not an asset.
