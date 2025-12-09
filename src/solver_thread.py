# src/solver_thread.py
from PyQt5.QtCore import QThread, pyqtSignal
import traceback

# on importe ici la fonction build_solve que tu as : capital_budgeting_extended.build_solve
from capital_budgeting_extended import build_solve

class SolverThread(QThread):
    """
    Thread qui exécute build_solve(...) et renvoie le résultat via signal.
    Il évite de bloquer l'UI principale.
    """
    finished = pyqtSignal(dict)        # emission: {'status':'ok', 'solutions':..., 'msg': ''}
    error = pyqtSignal(str)            # emission: exception string

    def __init__(self, df, budget, resource_caps=None, groups_exclusive=None,
                 dependencies=None, region_min_max=None, K=None,
                 time_limit=30, pool_solutions=0, multi_crit_alpha=1.0):
        super().__init__()
        self.df = df.copy()
        self.budget = budget
        self.resource_caps = resource_caps
        self.groups_exclusive = groups_exclusive
        self.dependencies = dependencies
        self.region_min_max = region_min_max
        self.K = K
        self.time_limit = time_limit
        self.pool_solutions = pool_solutions
        self.multi_crit_alpha = multi_crit_alpha

    def run(self):
        try:
            # Appel à ta fonction build_solve (Gurobi)
            res = build_solve(self.df,
                              budget=self.budget,
                              resource_caps=self.resource_caps,
                              groups_exclusive=self.groups_exclusive,
                              dependencies=self.dependencies,
                              region_min_max=self.region_min_max,
                              K=self.K,
                              time_limit=self.time_limit,
                              pool_solutions=self.pool_solutions,
                              multi_crit_alpha=self.multi_crit_alpha)
            # renvoyer le dictionnaire tel quel
            self.finished.emit({'status': 'ok', 'result': res})
        except Exception as e:
            tb = traceback.format_exc()
            self.error.emit(f"Solver error: {str(e)}\n{tb}")
