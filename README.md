# Projet-RO — Capital Budgeting (Python / Gurobi / PyQt)

This repository implements a small capital budgeting application (research / teaching prototype) that
lets you import a project portfolio (CSV), configure simple solver parameters and constraints,
then solve a 0-1 integer programming model (select projects) using Gurobi. A desktop GUI (PyQt5)
wraps the solver and provides interactive plotting of the selected projects.

---

## High-level overview

- The core optimization logic is in `src/capital_budgeting_extended.py` (function `build_solve`).
  - It builds a binary (0/1) integer model that maximizes benefit under budget and resource constraints.
  - Supports: budget limit, resource capacities (e.g. labour, land), exclusivity groups, dependencies,
    regional minimum/maximum quotas, cardinality (K), time limit, and solution pool.
  - Multi-criteria: you can mix `benefit` and `social_score` via the `multi_crit_alpha` parameter.
  - Returns a dictionary with the Gurobi `model` and a `solutions` list (each solution: selected IDs & objective).

- The GUI is implemented in `src/ihm_main.py` (a PyQt5 QWidget application).
  - Import/export CSV, edit the table, add/remove rows, quick validation.
  - Configure solver parameters (budget, time limit, pool size) and start/stop the solver.
  - Results area shows objective and number of selected projects and draws a chart of the selected projects.
  - Solver runs on a background thread (`src/solver_thread.py`) to keep the UI responsive.

- Utility helpers are in `src/ui_utils.py` (DataFrame <-> QTableWidget conversion, CSV load/save).

- Example data: `data/projects_example.csv` — contains sample projects with columns used by the solver.

- Notebooks in `notebooks/` provide analysis examples (`analysis.ipynb`) that call `build_solve` directly.

---

## What it does (user-facing)

From the UI you can:

- Import a CSV file containing the project list (columns: `proj_id`, `name`, `cost`, `benefit`, `region`, `requires`, `exclusive_group`, `labour`, `land`, `priority`, `social_score`, ...).
- Edit the table in-place: modify values, add rows (auto-generates `proj_id`), delete rows.
- Validate the dataset using the "Validation rapide" button; basic checks for duplicate IDs and numeric columns are performed.
- Set solver parameters:
  - `Budget total` (numeric)
  - `TimeLimit (s)` — max seconds Gurobi will run
  - `Pool solutions` — number of pool solutions to request (0 = off)
- Run the solver (`Optimiser`) — runs Gurobi in a background thread and updates the UI when finished.
- Stop the running solver (best-effort) with the `Annuler (stop)` button.
- See the best solution and (if available) pool solutions; view a chart of selected projects (regional distribution or benefit per project).
- Save the edited table back to a CSV via `Enregistrer CSV`.

---

## Algorithm / Solver
The solver constructs a binary integer program with one decision variable per project and maximizes aggregated benefit subject to budget, resource, exclusivity, dependency and regional constraints. Gurobi then runs presolve and a branch-and-bound search with heuristics and cutting planes to find and (if possible) prove an optimal integer solution. Multiple alternatives can be requested via Gurobi's solution pool (PoolSolutions) or enumerated using an exclusion-cut wrapper (enumerate_k_best). Note that collecting multiple diverse solutions depends on model structure, solver time, and pool parameters; therefore requesting N solutions does not guarantee N will be returned."


## Installation (recommended)

This project requires Python 3.8+ and the following packages:

- pandas
- matplotlib
- PyQt5
- gurobipy (Gurobi Python API) — requires a valid Gurobi install and license

Because `gurobipy` depends on Gurobi being installed separately, we recommend creating a conda environment.

Windows (example):

```cmd
REM Create and activate environment
conda create -n ro-gurobi python=3.10 -y
conda activate ro-gurobi

REM Install Python packages (PyPI where appropriate)
pip install pandas matplotlib PyQt5

REM Install Gurobi following Gurobi instructions for your platform and ensure the `gurobipy` package is available
REM (Often provided by conda or Gurobi installer). After installation, verify with: python -c "import gurobipy; print(gurobipy.gurobi.version())"
```

Notes:
- If you cannot use Gurobi, you can still run the GUI and import data, but the optimizer will fail when invoked.
- If you use a different solver (e.g., CBC, CPLEX), adapt `capital_budgeting_extended.py` accordingly.

---

## Quick start (running the GUI)

From the repository root (Windows `cmd.exe`):

```cmd
cd C:\Users\ayaga\Documents\GL3\academics\RO\Projet-RO
conda activate ro-gurobi    REM if you use conda
python src\ihm_main.py
```

Then in the GUI:
- Click `📥 Importer CSV` and select `data/projects_example.csv` (or your file).
- Optionally edit rows or add new projects with `➕ Ajouter ligne`.
- Set a `Budget total` or leave the placeholder value.
- Set `TimeLimit (s)` (e.g., 30) and `Pool solutions` (0 or >0).
- Click `🚀 Optimiser` to run the solver.
- When finished the results area will display the objective and selected projects. The plot will show a regional distribution or the benefits per project.

---

## CSV file format

The example CSV `data/projects_example.csv` uses these columns (common ones for the solver):

- `proj_id` (string): unique identifier of the project (e.g. P01)
- `name` (string): human-friendly project name
- `cost` (numeric): project cost (used in budget constraint)
- `benefit` (numeric): economic benefit (objective)
- `region` (string): region name (used for regional quotas / plotting)
- `requires` (string): semicolon-separated project ids that this project requires (dependencies)
- `exclusive_group` (string): group id to create mutual-exclusion among projects with the same group
- `labour`, `land` (numeric): resource consumption columns (used if `resource_caps` configured)
- `priority` (int): optional priority indicator
- `social_score` (numeric): optional secondary objective used when `multi_crit_alpha != 1`

When editing in the GUI the table is converted to a DataFrame before calling the solver; ensure numeric columns are valid numbers.

---

## Developer notes (core files)

- `src/capital_budgeting_extended.py` — core model builder and solver wrapper. Key functions:
  - `read_projects(csv_path)` — load and clean CSV
  - `build_solve(df, budget, resource_caps=..., pool_solutions=..., time_limit=..., multi_crit_alpha=...)` — build and solve model, return `{'model': m, 'solutions': [...]}`.
  - The file contains example runner code in `if __name__ == '__main__':` for quick CLI testing.

- `src/ihm_main.py` — PyQt5 GUI application. Key methods:
  - `load_csv(path)` — load CSV into the table
  - `on_import()` / `on_save()` / `on_add_row()` / `on_delete_row()` — UI actions
  - `on_solve()` — gathers options and starts `SolverThread`
  - `on_solver_finished(payload)` — handles solver output and updates the UI
  - `plot_selection(selected)` — draws a Matplotlib plot in the GUI

- `src/solver_thread.py` — QThread wrapper that runs `build_solve(...)` and emits signals on completion or error.

- `src/ui_utils.py` — helper functions:
  - `df_to_qtable(table_widget, df)`
  - `qtable_to_df(table_widget)`
  - `load_csv_to_df(path)`
  - `save_df_to_csv(df, path)`

- `data/projects_example.csv` — example dataset with many fields; good for initial testing.

---

## Troubleshooting

- "GurobiError: Unrecognized argument to getAttr":
  - Older/newer Gurobi versions expose solution pool attributes differently. This project contains a robust reader in `capital_budgeting_extended.py` that attempts several fallbacks. If you still see errors, please paste the full traceback and your Gurobi version.

- No solutions returned or `Aucune solution trouvée`:
  - Model may be infeasible under the specified budget/resources/quotas. Use `on_validate()` to check data quality, or lower constraints (increase budget) or relax resource caps.
  - Increase `TimeLimit` to give the solver more time (the pool search may need longer than the default).

- GUI does not start or PyQt missing:
  - Install `PyQt5` (`pip install PyQt5`) or use conda (`conda install pyqt`).

- `gurobipy` import fails:
  - Ensure Gurobi is installed and licensed on your machine. Follow Gurobi installation docs for Windows and add the Python package to your environment.

---

## Example: run the CLI test

You can run a quick CLI test of the solver (no GUI) by running the example runner inside `src/capital_budgeting_extended.py`:

```cmd
python -c "from src.capital_budgeting_extended import read_projects, build_solve; df = read_projects('data/projects_example.csv'); print(build_solve(df, budget=2000000, resource_caps={'labour':2000,'land':4000}, time_limit=30, pool_solutions=0))"
```

Note: depending on how your `PYTHONPATH`/package structure is set up you might need to run with `python src/capital_budgeting_extended.py` or `python -m src.capital_budgeting_extended`.

---

## Next steps / Ideas (optional)

- Add a proper constraints editor in the GUI for resource caps, regional min/max, and exclusivity groups.
- Add export of selected solution to Excel / PDF.
- Add unit tests for `build_solve` model building and solution parsing.
- Add sample scenarios and a scenario manager (preserve solver parameters per scenario).

---

If you want, I can now:

- Add a short walkthrough GIF/screencast showing the GUI usage,
- Add unit tests or a small CLI demo script that runs several budgets and saves the results,
- Extend the GUI to allow editing resource caps and regional quotas.

Tell me which next step you'd like.
