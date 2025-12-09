import gurobipy as gp
from gurobipy import GRB

m = gp.Model("test")
x = m.addVar(vtype=GRB.BINARY, name="x")
m.setObjective(x, GRB.MAXIMIZE)
m.addConstr(x <= 1)
m.optimize()
print("x=", x.X, "Obj=", m.ObjVal)
