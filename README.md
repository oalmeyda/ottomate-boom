# Ottomate Boom

Classic Minesweeper challenge with synchronized daily challenges, competitive leaderboards, and speedrun statistics for the [Ottomate Gaming Platform](https://ottomate-gaming-platform.web.app).

## Features

- **Classic 3 Board Sizes**:
  - **Beginner**: 9x9 grid, 10 mines
  - **Intermediate**: 16x16 grid, 40 mines
  - **Expert**: 16x30 grid (30 columns x 16 rows), 99 mines
- **Daily Challenge Mode**:
  - Deterministic daily boards generated from UTC date and difficulty.
  - Compete on the daily leaderboard for fastest completion time.
  - Seamlessly integrates with the Ottomate Hub Action Center.
- **Casual / Practice Mode**:
  - Instant casual boards for all 3 sizes with single-click restarts.
- **Classic Gameplay & Polish**:
  - Safe first-click rule: Guaranteed empty (0) opening cell with flood-fill cascade.
  - Chord clicking on satisfied numbered cells.
  - Mobile touch support with Flag Mode toggle button and long-press.
  - Digital 7-segment LED displays for remaining mines and elapsed seconds.
  - Reactive status face button (🙂 / 😮 / 😵 / 😎).
- **Comprehensive Leaderboards & Stats**:
  - Daily & all-time leaderboards filterable by difficulty.
  - Career stats: win rate %, best times, average times, win streaks, 3BV efficiency.

## Local Development

```bash
# Clone or navigate to repository
cd /home/ottomate/code/ottomate-boom

# Install with vendored wheel and development dependencies
pip install --find-links wheels -e ".[dev]"
# Or in editable mode with sibling ottomate-core:
pip install -e ../ottomate-core -e ".[dev]"

# Run tests
pytest

# Start local development server
uvicorn app.main:app --reload --port 8080
```
