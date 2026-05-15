# Site Preview

The public site uses Docusaurus under `apps/site/`. The homepage keeps the
custom Elephant Agent presentation, while the public docs stay on standard Docusaurus
layouts with brand-level theming layered through config and CSS.

The site remains the public companion to the canonical CLI-first path:

- `curl -fsSL https://elephant.agentic-in.ai/install.sh | bash`
- `elephant init`
- `elephant wake`
- `elephant status`
- `elephant herd new nova`
- `elephant herd`

## Local Commands

Use Node 20 locally so your dev, typecheck, and build behavior matches CI and Netlify. The frontend apps now declare `node: 20.x`, and local installs enforce that version via app-local `.npmrc` files.

From the repository root:

```bash
make site-install
make site-dev
make site-build
make preview
```

- `make site-install` installs the local Docusaurus dependencies with `npm ci`
- `make site-dev` runs the Docusaurus authoring server
- `make site-build` builds the deployable static site into `apps/site/dist/`
- `make preview` builds first and then serves the generated output locally

`make site-install` runs the repo-local postinstall patch in
`apps/site/scripts/patch-docusaurus-bundler.mjs`, which disables a broken
webpack progress UI path without changing the generated site output.

Default preview URL:

- `http://127.0.0.1:4180`
- if `4180` is busy, `make preview` automatically picks the next free port

Override the port if needed:

```bash
PORT=8080 make preview
```

## Content Sync

The public installer at `https://elephant.agentic-in.ai/install.sh` is copied from
repo root `install.sh` into `apps/site/static/install.sh` before build, so the
site and the repo stay aligned on the advertised install surface. That root
installer now tracks the latest published `elephant` dev package by default
and supports `--channel stable` for the latest stable publish.

## Build Artifact

`make site-build` produces static output in `apps/site/dist/`.

That output is what local preview, Docker preview deploy, CI smoke tests, and
Netlify publish.

## Netlify

`netlify.toml` runs `make site-build` and publishes `apps/site/dist/`.

The Netlify build also pins a compatible Node version for Docusaurus so the same
static output path is used locally and in hosted preview deploys.
