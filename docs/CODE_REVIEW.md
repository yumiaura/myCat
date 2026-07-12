# Code review — 2026-07-12

## High priority

1. `shop_api.py` accepts catalog character IDs as file names. Validate IDs as strict slugs and ensure resolved download/preview destinations remain below their intended cache or characters directory.
2. Do not forward a bearer token to arbitrary absolute download URLs or CDN redirects from the catalog. Send authorization only to the configured trusted API origin.
3. The shop is implemented but its only menu entry is commented out in `main.py`; either expose and secure it or remove the dormant path before release.

## Medium priority

1. Enforce compressed and uncompressed ZIP, frame-count, and decoded-pixel limits before loading character packs to avoid archive/image decompression denial-of-service.
2. Stream and size-limit preview downloads, validate image content before passing it to Qt, and honor/remove the unused catalog cache TTL.
3. ComfyUI uploads reference photos to its server input directory without cleanup. Tell users clearly and add cleanup when the target server supports it.
4. Validate persisted generation settings (notably `steps`) and fall back safely when config is malformed.

## Maintainability

`main.py` currently combines overlay rendering, application state, menus, and feature-controller wiring. Incrementally extract context-menu actions, character rendering/state, and bootstrap/controller wiring into focused modules.

## Test environment

The suite currently reports 203 passing and 4 environment-dependent failures: three calendar tests need `mycat[calendar]`; one updater test assumes import from a git checkout.
