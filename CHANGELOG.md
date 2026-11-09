# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
