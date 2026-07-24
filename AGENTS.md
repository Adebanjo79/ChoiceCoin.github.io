# Choice Coin Public Website

Community-managed static website for Choice Coin (deployed to `choice-coin.com` via GitHub Pages).

## Cursor Cloud specific instructions

- This is a purely static site: plain `.html` files at the repo root (`index.html`, `About.html`, `Docs.html`, `Participation.html`) plus images. There is no package manager, build step, test suite, or lint config, and no dependencies to install.
- TailwindCSS is loaded from a CDN inside the HTML, so styling requires network access at page-load time; there is no local CSS build.
- To run it in development, serve the repo root as static files, e.g. `python3 -m http.server 8000`, then open `http://localhost:8000/index.html`. Do not "build" — there is nothing to compile.
- Deployment is handled by GitHub Pages (`CNAME` = `choice-coin.com`); no CI/build is required to preview locally.
