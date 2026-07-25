# Vendored API-docs assets

Swagger UI and ReDoc are served from this directory instead of cdn.jsdelivr.net,
so `/docs` and `/redoc` load no third-party JavaScript (developers paste live
bearer tokens into these pages), work in air-gapped networks, and can run under
a strict Content-Security-Policy (see `core/middleware.py`).

| File                   | Package         | Version | Source                                                              |
| ---------------------- | --------------- | ------- | ------------------------------------------------------------------- |
| `swagger-ui-bundle.js` | swagger-ui-dist | 5.32.11 | https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.11/swagger-ui-bundle.js |
| `swagger-ui.css`       | swagger-ui-dist | 5.32.11 | https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.11/swagger-ui.css |
| `redoc.standalone.js`  | redoc           | 2.5.3   | https://cdn.jsdelivr.net/npm/redoc@2.5.3/bundles/redoc.standalone.js |
| `favicon.png`          | (local)         | –       | generated placeholder; replace with your own                        |

SHA-256 checksums of the vendored files:

```
1320f442151c57c447d3b70c7ffc6c4f86d08464020fe34c8cc5d3164e9944f0  redoc.standalone.js
fcb81e2c79e7e3b76ddb9bd7fc791552045040fde05c19d3f98f9213e7f7724d  swagger-ui-bundle.js
ca238f7d7c2cf4480c1e77a9c3b9da915ab216e96ffd354e69076560c650c6de  swagger-ui.css
```

## Updating

Pin an exact version (never a floating `@5` / `@2` tag) and re-download:

```bash
cd src/*/core/static
curl -sL -o swagger-ui-bundle.js "https://cdn.jsdelivr.net/npm/swagger-ui-dist@<version>/swagger-ui-bundle.js"
curl -sL -o swagger-ui.css      "https://cdn.jsdelivr.net/npm/swagger-ui-dist@<version>/swagger-ui.css"
curl -sL -o redoc.standalone.js "https://cdn.jsdelivr.net/npm/redoc@<version>/bundles/redoc.standalone.js"
shasum -a 256 *.js *.css   # refresh the table above
```

Then load `/docs` and `/redoc` locally and confirm both render and can execute
a request ("Try it out") before committing.
