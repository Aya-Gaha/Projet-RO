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
                pool_gap=None,
                multi_crit_alpha=1.0,
                exclude_sets=None):
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
    pool_gap: optional float, relative tolerance for accepting pool solutions (e.g. 0.05 means accept solutions up to 5% worse)
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

    # CRITICAL: Reset pool-related params to defaults ALWAYS (avoid stale state)
    try:
        m.Params.PoolSearchMode = 0
        m.Params.PoolSolutions = 0
    except Exception:
        pass

    # If user explicitly requested solution pool, enable it
    if pool_solutions and pool_solutions > 0:
        m.Params.PoolSearchMode = 2
        m.Params.PoolSolutions = pool_solutions
        try:
            # PoolGap controls how suboptimal pool members can be (None -> default)
            if pool_gap is not None:
                m.Params.PoolGap = pool_gap
            else:
                # default to allowing suboptimal pool solutions (1.0) if not specified
                m.Params.PoolGap = 1.0
            m.Params.MIPFocus = 1      # focus on finding diverse solutions
            m.Params.NumericFocus = 1  # stabilize pool solution extraction
        except Exception:
            pass
    else:
        # if user provided pool_gap but didn't request pool_solutions, still set parameter
        if pool_gap is not None:
            try:
                m.Params.PoolGap = pool_gap
            except Exception:
                pass

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

    # Exclude exact previous selections (useful for K-best enumeration)
    if exclude_sets:
        for ex_idx, ex_set in enumerate(exclude_sets):
            members = [p for p in ex_set if p in projects]
            if members:
                # forbid selecting all members at once (force at least one different choice)
                m.addConstr(gp.quicksum(x[p] for p in members) <= len(members) - 1, name=f'Exclude_{ex_idx}')

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

    # Collect best solution (and pool if explicitly requested)
    solutions = []
    if m.Status in {GRB.OPTIMAL, GRB.SUBOPTIMAL, GRB.TIME_LIMIT}:
        # ONLY read pool solutions if user explicitly requested them (pool_solutions > 0)
        if pool_solutions and pool_solutions > 0 and getattr(m, 'SolCount', 0) > 0:
            # Deterministically read up to pool_solutions solutions from the pool
            avail = int(getattr(m, 'SolCount', 0))
            take = int(min(avail, pool_solutions))

            # Get all pool objective values at once using getAttr
            try:
                pool_objs = m.getAttr(GRB.Attr.PoolObjVal, m.getVars())
            except Exception:
                pool_objs = None
            
            # If that didn't work, try via a list comprehension after setting SolutionNumber
            if pool_objs is None or not isinstance(pool_objs, (list, tuple)):
                pool_objs = []
                for s in range(take):
                    try:
                        m.setParam('SolutionNumber', s)
                        obj = m.PoolObjVal if hasattr(m, 'PoolObjVal') else m.ObjVal
                        pool_objs.append(obj)
                    except Exception:
                        pool_objs.append(m.ObjVal)

            for s in range(take):
                # Set current solution number for Gurobi to read from pool
                try:
                    m.setParam('SolutionNumber', s)
                except Exception:
                    try:
                        m.Params.SolutionNumber = s
                    except Exception:
                        pass

                # Read variable values for this pool solution using getAttr with SolutionNumber
                sel = []
                try:
                    # Try to read X values for this specific solution
                    var_vals = m.getAttr('X', m.getVars())
                    for var, val in zip(m.getVars(), var_vals):
                        if val > 0.5:
                            # Extract project ID from var name (handle 'x_P01' or 'x[P01]' formats)
                            vname = var.VarName
                            if 'P' in vname:
                                proj_id = vname.split('P')[-1].replace(']', '').replace('_', '')
                                sel.append('P' + proj_id)
                except Exception:
                    # Fallback: read individual variables
                    for p in projects:
                        var = x[p]
                        val = None
                        # Try Xn first (pool solution value)
                        if hasattr(var, 'Xn'):
                            try:
                                val = var.Xn
                            except Exception:
                                val = None
                        # Fall back to X
                        if val is None:
                            try:
                                val = var.X
                            except Exception:
                                val = 0
                        if val is not None and val > 0.5:
                            sel.append(p)

                # Read objective value for this pool solution
                obj = pool_objs[s] if s < len(pool_objs) else m.ObjVal

                solutions.append({'sol_no': s, 'selected': sel, 'obj': float(obj)})

        else:
            # Single best solution ONLY (when pool_solutions == 0 or no solutions found)
            sel = [p for p in projects if x[p].X > 0.5]
            solutions.append({'sol_no': 0, 'selected': sel, 'obj': float(m.ObjVal)})

    # Deduplicate solutions that have identical selected sets (preserve order)
    unique = []
    seen = set()
    for sol in solutions:
        key = tuple(sorted(sol.get('selected', [])))
        if key in seen:
            continue
        seen.add(key)
        unique.append(sol)

    # attach some metadata about how many pool solutions Gurobi reported
    pool_meta = {'gurobi_solcount': int(getattr(m, 'SolCount', 0)), 'requested_pool': int(pool_solutions)}

    # FALLBACK: If user requested pool solutions but Gurobi found too few,
    # automatically run K-best enumeration to provide the requested alternatives
    if pool_solutions and pool_solutions > 0 and len(unique) < pool_solutions:
        fallback_k = pool_solutions
        fallback_res = enumerate_k_best(
            df,
            budget=budget,
            resource_caps=resource_caps,
            groups_exclusive=groups_exclusive,
            dependencies=dependencies,
            region_min_max=region_min_max,
            K=K,
            time_limit=time_limit,
            k=fallback_k,
            time_per_solve=time_limit if time_limit else 30,
            multi_crit_alpha=multi_crit_alpha
        )
        # Replace with enumeration results (they are complete and distinct)
        enum_sols = fallback_res.get('solutions', [])
        if enum_sols:
            unique = enum_sols[:pool_solutions]

    return {'model': m, 'solutions': unique, 'pool_meta': pool_meta}


def enumerate_k_best(df,
                     budget,
                     resource_caps=None,
                     groups_exclusive=None,
                     dependencies=None,
                     region_min_max=None,
                     K=None,
                     time_limit=None,
                     k=3,
                     time_per_solve=None,
                     multi_crit_alpha=1.0):
    """Enumerate up to `k` distinct best solutions by repeatedly solving and
    adding an exclusion constraint forbidding previously found selections.

    This is a wrapper that repeatedly calls `build_solve` and does not alter
    the core model logic; it only adds exclusion constraints between iterations.
    Returns a dict with key 'solutions' containing up to k solution dicts.
    """
    found = []
    exclude_sets = []
    # time_per_solve allows shorter solves per enumeration if desired
    per_solve = time_per_solve if time_per_solve is not None else time_limit

    for i in range(k):
        res = build_solve(df,
                          budget=budget,
                          resource_caps=resource_caps,
                          groups_exclusive=groups_exclusive,
                          dependencies=dependencies,
                          region_min_max=region_min_max,
                          K=K,
                          time_limit=per_solve,
                          pool_solutions=0,
                          multi_crit_alpha=multi_crit_alpha,
                          exclude_sets=exclude_sets)

        sols = res.get('solutions', [])
        if not sols:
            break

        best = sols[0]
        # Ensure sol_no is sequential within the enumeration (avoid repeated 0s)
        entry = dict(best)
        entry['sol_no'] = i

        # attach some metadata about the iteration
        entry['_iteration'] = i
        entry['_excluded'] = list(exclude_sets)  # copies of exclude sets used so far
        # append found solution and then exclude it in next iterations
        found.append(entry)

        sel = best.get('selected', [])
        if not sel:
            break
        exclude_sets.append(sel)

    return {'solutions': found}

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
