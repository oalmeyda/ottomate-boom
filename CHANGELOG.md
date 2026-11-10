# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-11-10

### Added
- **Core Grid Engine Integration (`app/services/boom_engine.py`)**:
  - Delegated board neighbor coordinate resolution (`get_neighbors`) to `ottomate_core.grid_engine.get_grid_neighbors`.
- **Synthesized Web Audio Engine (`app/static/js/boom.js`, `index.html`)**:
  - Replaced local oscillator audio code with `/core-static/js/ottomate-audio.js`.
  - Wired clicks, mine explosion blast, and victory fanfare.
- **Shared API Helper**:
  - Delegated `apiFetch` in `boom.js` to `window.Ottomate.api()`.
- **Copier Answers Alignment**:
  - Synchronized `.copier-answers.yml` to clean template ref `v1.28.4`.

### Changed
- **Upgraded Core Dependency**: Bumped to `ottomate-core>=1.28.4` with automated cache-buster query verification.
- **Cache-Busting Asset Alignment (`index.html`)**: Aligned all static asset query parameters to `?v=0.1.4`.

## [0.1.3] - 2026-11-09

### Fixed
- **Win Banner Layout & Leaderboard Button Overlap**:
  - Restructured `.win-banner` with flex-wrap and responsive gap (`gap: 0.85rem 1.25rem`) between `.win-banner-body` and `.win-banner-actions`.
  - Added `flex: 1 1 260px; min-width: 0;` and word wrapping to `.win-subtitle` to prevent long status text from extending beneath the "View Leaderboard" button.
  - Added dedicated styling for `.btn-win-leaderboard` with clear spacing and mobile full-width stacking under 640px.

## [0.1.2] - 2026-11-09

### Fixed
- **Snug Board Frame & Zero-Void Layout**:
  - Replaced 100%-width block layout with `display: inline-flex; width: fit-content; max-width: 100%; margin: 0 auto;` on `.minesweeper-window`.
  - Configured `.minesweeper-grid` to `display: inline-grid; width: max-content;` and `.board-scroll-container` to `width: fit-content; max-width: 100%; margin: 0 auto;`.
  - Window frame and top HUD now wrap snugly around the exact grid width across all 3 board sizes (Beginner 9x9, Intermediate 16x16, Expert 30x16), eliminating the empty dark void to the right of the grid.
  - Centered `.boom-toolbar` and constrained `#win-banner` to fit board width.
- **Header Auth & Profile Lifecycle**:
  - Delegated header profile and auth button toggling to `Ottomate.updateProfilePill(user)` and `Ottomate.toggleAuthButtons(true/false)`.
  - Upgraded to `ottomate-core>=1.28.1`, suppressing all competing sign-in links ("Sign in with Email", Google Sign-In) once authenticated.

## [0.1.1] - 2026-11-09

### Fixed
- **Google Sign-In & Auth Integration**: Integrated `Ottomate.setupSignIn` and `Ottomate.renderGoogleSignIn` to render the Google Sign-In button in both the header and the guest card.
- **Authenticated API Fetch**: Routed all data calls (`/api/me`, `/api/daily/status`, `/api/game/finish`, `/api/stats`, `/api/history`, `/api/leaderboard`) through `apiFetch` with `Authorization: Bearer <token>`.
- **Domain Migration to `ottomate-boom.web.app`**: Updated canonical service URL from `ottomate-game-boom.web.app` to `ottomate-boom.web.app`.
- **People & Profile Modals**: Integrated with `Ottomate.people` for unified Directory and Profile modal dialogs.

## [0.1.0] - 2026-11-09

### Added
- **Initial Ottomate Boom Service Launch**: Classic Minesweeper game engine and web application.
- **Classic 3 Board Sizes**:
  - Beginner: 9x9 grid with 10 mines.
  - Intermediate: 16x16 grid with 40 mines.
  - Expert: 16x30 grid (30 cols, 16 rows) with 99 mines.
- **Daily Challenge Mode**: Synchronized daily deterministic puzzle seeded from the UTC date (`YYYY-MM-DD`) and difficulty, enabling fair competition across all players.
- **Safe First-Click Engine**: Deterministic mine relocation guarantees first-clicked cell and its immediate 8 neighbors are never mines, providing a guaranteed satisfying opening cascade.
- **Advanced Minesweeper Controls**: Left-click to dig, right-click/long-press to flag, flag mode toggle for touch/mobile devices, and chord clicking (revealing unflagged neighbors on satisfied numbers).
- **Interactive Retro HUD**: 3-digit LED flag counter, reactive status face button (🙂 / 😮 / 😵 / 😎), and 3-digit digital timer.
- **Leaderboards & Player Statistics**: Scoped views (`daily` and `all_time`) filterable by difficulty (`all`, `beginner`, `intermediate`, `expert`), tracking games played, wins, win rate %, fastest solve times, average times, win streaks (`StreakTracker`), and 3BV efficiency.
- **Ottomate Hub Action Center Integration**: Automatic synchronization via `sync_daily_pending_action` and `record_daily_completed("boom", user_email, date_str)` when daily challenges are cleared.
- **Private Package Distribution**: Vendored `ottomate-core>=1.28.0` wheel, 3-tier RBAC, and multi-database Firestore isolation (`boom`).
