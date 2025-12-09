# src/capital_budgeting_extended.py
"""
Capital budgeting PLNE (extended)
Reads data from data/projects_example.csv and builds a generic PLNE:
- binary vars x[j] for each project j
- objective: maximize (weighted) benefit
- constraints: budget, resource capacities, exclusivity groups, dependencies,
               regional quotas (min/max), cardinality (K)
- supports multi-criteria weighting and solution pool
"""

import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from pathlib import Path

# ---------------------------
# Utility: read dataset
# ---------------------------
def read_projects(csv_path: str):
    df = pd.read_csv(csv_path, dtype={'proj_id': str})
    df.fillna('', inplace=True)
    # ensure numeric columns
    for col in ['cost', 'benefit', 'labour', 'land', 'social_score', 'priority']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

# ---------------------------
# Build & solve extended model
# ---------------------------
def build_solve(df,
                budget,
                resource_caps=None,
                groups_exclusive=None,
                dependencies=None,
                region_min_max=None,
                K=None,
                time_limit=None,
                pool_solutions=0,
                multi_crit_alpha=1.0):
    """
    df: DataFrame with at least columns ['proj_id','cost','benefit'] (others optional)
    budget: scalar
    resource_caps: dict {'labour': cap, 'land': cap, ...}
    groups_exclusive: list of lists of proj_id (mutually exclusive groups)
    dependencies: list of tuples (i,j) meaning j requires i
    region_min_max: dict {region: (min_projects, max_projects)} (use None for either)
    K: optional max number of projects
    time_limit: seconds
    pool_solutions: int (0 = off)
    multi_crit_alpha: weight for benefit in combined objective [0..1]
    """
    projects = df['proj_id'].tolist()
    cost = df.set_index('proj_id')['cost'].to_dict()
    benefit = df.set_index('proj_id')['benefit'].to_dict()

    # Build combined benefit if multi-criteria requested
    if 'social_score' in df.columns:
        social = df.set_index('proj_id')['social_score'].to_dict()
        # normalize benefit and social_score to [0,1] to combine sensibly
        b_vals = pd.Series(benefit)
        s_vals = pd.Series(social)
        b_norm = (b_vals - b_vals.min()) / (b_vals.max() - b_vals.min() + 1e-9)
        s_norm = (s_vals - s_vals.min()) / (s_vals.max() - s_vals.min() + 1e-9)
        combined = {}
        for p in projects:
            combined[p] = float(multi_crit_alpha * b_norm.loc[p] + (1.0 - multi_crit_alpha) * s_norm.loc[p])
        # scale combined back to similar magnitude as original benefits (optional)
        # multiply by average benefit to keep magnitudes reasonable
        avg_b = b_vals.mean() if len(b_vals)>0 else 1.0
        benefit_used = {p: combined[p] * avg_b for p in projects}
    else:
        benefit_used = benefit

    m = gp.Model("CapitalBudget_Extended")
    # parameters
    if time_limit is not None:
        m.Params.TimeLimit = time_limit
    if pool_solutions and pool_solutions > 0:
        m.Params.PoolSearchMode = 2
        m.Params.PoolSolutions = pool_solutions

    # decision variables
    x = m.addVars(projects, vtype=GRB.BINARY, name='x')

    # objective
    m.setObjective(gp.quicksum(benefit_used[p] * x[p] for p in projects), GRB.MAXIMIZE)

    # budget constraint
    m.addConstr(gp.quicksum(cost[p] * x[p] for p in projects) <= budget, name='Budget')

    # cardinality
    if K is not None:
        m.addConstr(x.sum() <= K, name='Cardinality')

    # exclusivity groups
    if groups_exclusive:
        for idx, group in enumerate(groups_exclusive):
            members = [p for p in group if p in projects]
            if members:
                m.addConstr(gp.quicksum(x[p] for p in members) <= 1, name=f'Excl_{idx}')

    # dependencies
    if dependencies:
        for (i,j) in dependencies:
            if i in projects and j in projects:
                m.addConstr(x[j] <= x[i], name=f'Dep_{i}_{j}')

    # resources constraints: uses columns in df (e.g., 'labour', 'land')
    if resource_caps:
        for rname, cap in resource_caps.items():
            if rname in df.columns:
                cons = gp.quicksum(df.set_index('proj_id').loc[p, rname] * x[p] for p in projects)
                m.addConstr(cons <= cap, name=f'Resource_{rname}')

    # regional quotas (min,max)
    if region_min_max:
        # build mapping proj -> region
        if 'region' not in df.columns:
            raise ValueError("region_min_max specified but no 'region' column in df")
        region_map = df.set_index('proj_id')['region'].to_dict()
        # for each region constraint
        for region, (min_req, max_req) in region_min_max.items():
            members = [p for p in projects if region_map.get(p,'') == region]
            if members:
                if max_req is not None:
                    m.addConstr(gp.quicksum(x[p] for p in members) <= max_req, name=f'RegionMax_{region}')
                if min_req is not None and min_req > 0:
                    m.addConstr(gp.quicksum(x[p] for p in members) >= min_req, name=f'RegionMin_{region}')

    # optional: force selection of high-priority projects first (example)
    # e.g., ensure at least N priority==1 projects selected (if desired)
    if 'priority' in df.columns:
        # example: ensure at least one priority-1 project if any exist
        pr1 = df[df['priority']==1]['proj_id'].tolist()
        if pr1:
            # this is optional — comment/uncomment as desired
            # m.addConstr(gp.quicksum(x[p] for p in pr1) >= 1, name='MustOnePriority1')
            pass

    # Optimize
    m.optimize()

    # Collect best solution (and pool if used)
    solutions = []
    if m.Status in {GRB.OPTIMAL, GRB.SUBOPTIMAL, GRB.TIME_LIMIT}:
        if pool_solutions and m.SolCount > 0:
            # Iterate over available pool solutions (robust across Gurobi versions)
            for s in range(int(min(m.SolCount, pool_solutions))):
                # try to select solution number s
                try:
                    m.Params.SolutionNumber = s
                except Exception:
                    try:
                        m.setParam('SolutionNumber', s)
                    except Exception:
                        pass

                # read variable values for this pool solution; prefer Xn (pool value), fallback to X
                sel = []
                for p in projects:
                    var = x[p]
                    val = None
                    if hasattr(var, 'Xn'):
                        try:
                            val = var.Xn
                        except Exception:
                            val = None
                    if val is None:
                        # fallback to current solution value
                        try:
                            val = var.X
                        except Exception:
                            val = 0
                    if val is not None and val > 0.5:
                        sel.append(p)

                # read objective value for this pool solution with fallbacks
                obj = None
                if hasattr(m, 'PoolObjVal'):
                    try:
                        obj = m.PoolObjVal
                    except Exception:
                        obj = None
                if obj is None:
                    # try getAttr (older API) or fallback to ObjVal
                    try:
                        vals = m.getAttr(GRB.Attr.PoolObjVal)
                        if isinstance(vals, (list, tuple)) and s < len(vals):
                            obj = vals[s]
                        else:
                            obj = m.ObjVal
                    except Exception:
                        obj = m.ObjVal

                solutions.append({'sol_no': s, 'selected': sel, 'obj': float(obj)})

        else:
            sel = [p for p in projects if x[p].X > 0.5]
            solutions.append({'sol_no': 0, 'selected': sel, 'obj': float(m.ObjVal)})

    return {'model': m, 'solutions': solutions}

# ---------------------------
# Example runner / quick test
# ---------------------------
if __name__ == '__main__':
    base = Path(__file__).resolve().parents[1]
    csv = base / 'data' / 'projects_example.csv'
    df = read_projects(csv)

    # PARAMETERS (example)
    budget = 2000000  # total budget
    resource_caps = {'labour': 2000, 'land': 4000}  # example capacities
    # exclusivity groups (optional) - names matching exclusive_group column
    # Build groups from exclusive_group values in df
    groups = []
    if 'exclusive_group' in df.columns:
        for gname in df['exclusive_group'].unique():
            if gname and gname.strip():
                members = df[df['exclusive_group']==gname]['proj_id'].tolist()
                if members:
                    groups.append(members)
    # dependencies: parse 'requires' column (semicolon separated)
    deps = []
    if 'requires' in df.columns:
        for p, req in df.set_index('proj_id')['requires'].items():
            if isinstance(req, str) and req.strip():
                for r in req.split(';'):
                    r = r.strip()
                    if r:
                        deps.append((r, p))  # (i, j) meaning j requires i

    # regional quotas example: require at least 1 project in RegionD, at most 6 in RegionA
    region_quotas = {'RegionD': (1, None), 'RegionA': (None, 6)}

    res = build_solve(df,
                      budget=budget,
                      resource_caps=resource_caps,
                      groups_exclusive=groups,
                      dependencies=deps,
                      region_min_max=region_quotas,
                      K=None,
                      time_limit=60,
                      pool_solutions=0,
                      multi_crit_alpha=0.9)

    print("Solutions found:", res['solutions'])
