# src/capital_budgeting.py
import csv
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

def read_projects(csv_path):
    """Read projects CSV -> DataFrame expected columns:
       proj_id,cost,benefit,group,requires,region,resource_1,resource_2,... (optional)
       'requires' may be semicolon-separated list of proj_ids.
    """
    df = pd.read_csv(csv_path, dtype={'proj_id':str})
    df.fillna('', inplace=True)
    return df

def build_and_solve(df_projects,
                    budget,
                    resource_caps=None,
                    groups_exclusive=None,
                    dependencies=None,
                    K=None,
                    time_limit=None,
                    pool_solutions=0,
                    maximize=True):
    """
    df_projects: DataFrame with at least ['proj_id','cost','benefit']
    budget: scalar
    resource_caps: dict {resource_name: capacity} where resource columns exist in df (optional)
    groups_exclusive: list of lists, each inner list contains proj_id values that are mutually exclusive
    dependencies: list of tuples (i,j) meaning j requires i  (proj ids)
    K: optional max number of projects
    time_limit: seconds, optional
    pool_solutions: if >0, ask Gurobi to fill solution pool up to that many
    """
    projects = df_projects['proj_id'].tolist()
    cost = df_projects.set_index('proj_id')['cost'].to_dict()
    benefit = df_projects.set_index('proj_id')['benefit'].to_dict()

    m = gp.Model("CapitalBudgeting")
    # params
    if time_limit is not None:
        m.Params.TimeLimit = time_limit
    if pool_solutions and pool_solutions > 0:
        m.Params.PoolSearchMode = 2  # find diverse solutions
        m.Params.PoolSolutions = pool_solutions

    # decision vars (characteristic function)
    x = m.addVars(projects, vtype=GRB.BINARY, name='x')

    # objective
    if maximize:
        m.setObjective(gp.quicksum(benefit[p] * x[p] for p in projects), GRB.MAXIMIZE)
    else:
        m.setObjective(gp.quicksum(benefit[p] * x[p] for p in projects), GRB.MINIMIZE)

    # budget
    m.addConstr(gp.quicksum(cost[p] * x[p] for p in projects) <= budget, name='Budget')

    # cardinality
    if K is not None:
        m.addConstr(gp.quicksum(x[p] for p in projects) <= K, name='Cardinality')

    # exclusivity groups
    if groups_exclusive:
        for idx, group in enumerate(groups_exclusive):
            # ensure group members are in projects
            members = [p for p in group if p in projects]
            if members:
                m.addConstr(gp.quicksum(x[p] for p in members) <= 1, name=f'Excl_{idx}')

    # dependencies
    if dependencies:
        for (i,j) in dependencies:
            if i in projects and j in projects:
                m.addConstr(x[j] <= x[i], name=f'Dep_{i}_{j}')

    # resource constraints (resource_caps dict expected)
    if resource_caps:
        for rname, cap in resource_caps.items():
            if rname in df_projects.columns:
                cons = gp.quicksum(df_projects.set_index('proj_id').loc[p, rname] * x[p]
                                   for p in projects)
                m.addConstr(cons <= cap, name=f'Resource_{rname}')

    m.optimize()

    # collect best solution(s)
    sols = []
    if m.Status == GRB.OPTIMAL or m.Status == GRB.TIME_LIMIT or m.Status == GRB.SUBOPTIMAL:
        # if pool used:
        if pool_solutions and m.SolCount > 0:
            for s in range(min(int(m.SolCount), pool_solutions)):
                sol = {}
                m.setParam('SolutionNumber', s)
                selected = [p for p in projects if x[p].Xn > 0.5]  # Xn reads from solution s
                obj = m.PoolObjVal if s==0 and hasattr(m, 'PoolObjVal') else m.getObjective().getValue()
                sol['solution_no'] = s
                sol['selected'] = selected
                sol['objective'] = m.getAttr(GRB.Attr.PoolObjVal, s) if hasattr(m, 'PoolObjVal') else m.ObjVal
                sols.append(sol)
        else:
            selected = [p for p in projects if x[p].X > 0.5]
            sols.append({'solution_no': 0, 'selected': selected, 'objective': m.ObjVal})

    return {'model': m, 'solutions': sols}

if __name__ == '__main__':
    # Example usage with CSV file
    df = read_projects('data/projects_example.csv')
    # parse optional fields (example)
    # groups_exclusive = [['P1','P2'], ['P7','P8']]
    # dependencies = [('P3','P5')]  # P5 requires P3
    res = build_and_solve(df_projects=df,
                          budget=1000000,
                          resource_caps=None,
                          groups_exclusive=None,
                          dependencies=None,
                          K=None,
                          time_limit=30,
                          pool_solutions=0)
    print("Best solution objective:", res['solutions'][0]['objective'])
    print("Selected projects:", res['solutions'][0]['selected'])
