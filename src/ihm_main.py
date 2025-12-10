# src/ihm_main.py
import sys
import os
from pathlib import Path

import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox, QTableWidget, QLabel, QLineEdit, QSpinBox, QGroupBox, QTableWidgetItem,
    QPlainTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from ui_utils import df_to_qtable, qtable_to_df, load_csv_to_df, save_df_to_csv
from solver_thread import SolverThread

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CSV = BASE_DIR / 'data' / 'projects_example.csv'

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projet-RO — Capital Budgeting (IHM)")
        self.resize(1200, 750)

        # DataFrame en mémoire
        self.df = pd.DataFrame()
        # solver thread reference
        self.solver_thread = None
        self.last_solution = None
        # Pool solutions storage and navigation
        self.pool_solutions = []
        self.current_sol_idx = 0

        # Apply stylesheet for better aesthetics
        self.apply_stylesheet()

        # Layouts
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        bottom_layout = QHBoxLayout()

        # Table widget (centre)
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #f5f5f5;
                gridline-color: #cccccc;
                border: 1px solid #ddd;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #4a7ba7;
                color: white;
                padding: 5px;
                border: none;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.table, stretch=6)

        # Left: Data buttons
        left_v = QVBoxLayout()
        left_label = QLabel("Données")
        left_label.setFont(QFont("Arial", 11, QFont.Bold))
        left_label.setStyleSheet("color: #2c3e50;")
        left_v.addWidget(left_label)

        btn_import = QPushButton("Importer CSV")
        btn_import.clicked.connect(self.on_import)
        btn_import.setStyleSheet(self._button_style("#3498db"))
        left_v.addWidget(btn_import)

        btn_save = QPushButton("Enregistrer CSV")
        btn_save.clicked.connect(self.on_save)
        btn_save.setStyleSheet(self._button_style("#27ae60"))
        left_v.addWidget(btn_save)

        btn_add = QPushButton(" Ajouter ligne")
        btn_add.clicked.connect(self.on_add_row)
        btn_add.setStyleSheet(self._button_style("#f39c12"))
        left_v.addWidget(btn_add)

        btn_delete = QPushButton("Supprimer ligne")
        btn_delete.clicked.connect(self.on_delete_row)
        btn_delete.setStyleSheet(self._button_style("#e74c3c"))
        left_v.addWidget(btn_delete)

        btn_validate = QPushButton("✓ Validation rapide")
        btn_validate.clicked.connect(self.on_validate)
        btn_validate.setStyleSheet(self._button_style("#9b59b6"))
        left_v.addWidget(btn_validate)

        left_v.addStretch()
        top_layout.addLayout(left_v, stretch=1)

        # Mid: Solve controls
        mid_v = QVBoxLayout()
        mid_label = QLabel("Solveur")
        mid_label.setFont(QFont("Arial", 11, QFont.Bold))
        mid_label.setStyleSheet("color: #2c3e50;")
        mid_v.addWidget(mid_label)

        # budget input
        budget_box = QGroupBox("Paramètres du Solveur")
        budget_box.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3498db;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #2c3e50;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        budget_layout = QHBoxLayout()
        budget_label = QLabel("Budget total:")
        budget_label.setStyleSheet("color: #34495e; font-weight: bold;")
        self.budget_input = QLineEdit()
        self.budget_input.setPlaceholderText("2000000")
        self.budget_input.setStyleSheet("QLineEdit { padding: 5px; border: 1px solid #bdc3c7; border-radius: 3px; }")
        budget_layout.addWidget(budget_label)
        budget_layout.addWidget(self.budget_input)
        budget_box.setLayout(budget_layout)
        mid_v.addWidget(budget_box)

        # time limit and pool
        controls_layout = QHBoxLayout()
        timelimit_label = QLabel("TimeLimit (s):")
        timelimit_label.setStyleSheet("color: #34495e; font-weight: bold;")
        self.timelimit_input = QSpinBox()
        self.timelimit_input.setRange(1, 9999)
        self.timelimit_input.setValue(30)
        self.timelimit_input.setStyleSheet("QSpinBox { padding: 5px; border: 1px solid #bdc3c7; border-radius: 3px; }")
        controls_layout.addWidget(timelimit_label)
        controls_layout.addWidget(self.timelimit_input)

        pool_label = QLabel("Pool solutions:")
        pool_label.setStyleSheet("color: #34495e; font-weight: bold;")
        self.pool_input = QSpinBox()
        self.pool_input.setRange(0, 50)
        self.pool_input.setValue(0)
        self.pool_input.setStyleSheet("QSpinBox { padding: 5px; border: 1px solid #bdc3c7; border-radius: 3px; }")
        controls_layout.addWidget(pool_label)
        controls_layout.addWidget(self.pool_input)
        mid_v.addLayout(controls_layout)

        # Buttons Solve / Stop
        self.btn_solve = QPushButton(" Optimiser")
        self.btn_solve.clicked.connect(self.on_solve)
        self.btn_solve.setStyleSheet(self._button_style("#16a085", hover="#138d75"))
        self.btn_solve.setMinimumHeight(40)
        self.btn_solve.setFont(QFont("Arial", 10, QFont.Bold))
        mid_v.addWidget(self.btn_solve)

        self.btn_stop = QPushButton(" Annuler (stop)")
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(self._button_style("#c0392b", hover="#a93226"))
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.setFont(QFont("Arial", 10, QFont.Bold))
        mid_v.addWidget(self.btn_stop)

        mid_v.addStretch()
        top_layout.addLayout(mid_v, stretch=1)

        # Right: Results & Plot
        right_v = QVBoxLayout()
        right_label = QLabel("Résultats")
        right_label.setFont(QFont("Arial", 11, QFont.Bold))
        right_label.setStyleSheet("color: #2c3e50;")
        right_v.addWidget(right_label)

        self.result_label = QLabel("Résultat : (aucune exécution)")
        self.result_label.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                padding: 10px;
                border-radius: 4px;
                border: 1px solid #bdc3c7;
                color: #2c3e50;
                font-weight: bold;
            }
        """)
        right_v.addWidget(self.result_label)

        # Navigation buttons for pool solutions
        nav_layout = QHBoxLayout()
        self.btn_prev_sol = QPushButton("◄ Précédent")
        self.btn_prev_sol.clicked.connect(self.on_prev_solution)
        self.btn_prev_sol.setEnabled(False)
        self.btn_prev_sol.setStyleSheet(self._button_style("#95a5a6"))
        nav_layout.addWidget(self.btn_prev_sol)

        self.sol_counter_label = QLabel("Sol: 1/1")
        self.sol_counter_label.setStyleSheet("color: #34495e; font-weight: bold; text-align: center;")
        self.sol_counter_label.setAlignment(Qt.AlignCenter)
        nav_layout.addWidget(self.sol_counter_label)

        self.btn_next_sol = QPushButton("Suivant ►")
        self.btn_next_sol.clicked.connect(self.on_next_solution)
        self.btn_next_sol.setEnabled(False)
        self.btn_next_sol.setStyleSheet(self._button_style("#95a5a6"))
        nav_layout.addWidget(self.btn_next_sol)
        right_v.addLayout(nav_layout)

        # matplotlib canvas
        self.fig, self.ax = plt.subplots(figsize=(4, 3))
        self.fig.patch.set_facecolor('#f5f5f5')
        self.canvas = FigureCanvas(self.fig)
        self.solution_list = QPlainTextEdit()

        self.solution_list.setReadOnly(True)
        self.solution_list.setStyleSheet("""
            QPlainTextEdit {
                background-color: #ffffff;
                border: 1px solid #bdc3c7;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        right_v.addWidget(self.solution_list)

        # right_v.addWidget(self.canvas)

        top_layout.addLayout(right_v, stretch=1)

        main_layout.addLayout(top_layout, stretch=4)

        # Bottom area: logs / messages
        bottom_left = QVBoxLayout()
        log_title = QLabel("Journal d'exécution")
        log_title.setFont(QFont("Arial", 10, QFont.Bold))
        log_title.setStyleSheet("color: #2c3e50;")
        bottom_left.addWidget(log_title)
        
        # Use a fixed-height, read-only, scrollable text area for logs so the UI doesn't expand
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setFixedHeight(180)
        self.log_widget.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                padding: 8px;
                border-radius: 3px;
                font-family: Courier;
                font-size: 9pt;
            }
        """)
        bottom_left.addWidget(self.log_widget)
        bottom_layout.addLayout(bottom_left, stretch=2)

        bottom_right = QVBoxLayout()
        # Quick run buttons
        # btn_show_selected = QPushButton(" Afficher sélection")
        # btn_show_selected.clicked.connect(self.on_show_selected)
        # btn_show_selected.setStyleSheet(self._button_style("#3498db"))
        # bottom_right.addWidget(btn_show_selected)
        bottom_right.addWidget(self.canvas)
        bottom_layout.addLayout(bottom_right, stretch=1)

        main_layout.addLayout(bottom_layout, stretch=1)

        self.setLayout(main_layout)
        self.log(" Application démarrée. Cliquez sur 'Importer CSV' pour charger les données.")

    def apply_stylesheet(self):
        """Apply global stylesheet for the application."""
        self.setStyleSheet("""
            QWidget {
                background-color: #ecf0f1;
                color: #2c3e50;
                font-family: Arial;
                font-size: 10pt;
            }
            QLineEdit, QSpinBox {
                padding: 5px;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                background-color: white;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 2px solid #3498db;
            }
        """)

    def _button_style(self, bg_color="#3498db", hover="#2980b9"):
        """Generate button stylesheet with colors."""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                padding: 10px 10px 6px 14px;
            }}
            QPushButton:disabled {{
                background-color: #95a5a6;
                color: #7f8c8d;
            }}
        """

    # --------- Data operations ----------
    def load_csv(self, path):
        try:
            df = load_csv_to_df(path)
            self.df = df
            df_to_qtable(self.table, df)
            # === AJOUT : activer sauvegarde automatique après edition ===
            self.table.itemChanged.connect(self._auto_save_cell)
            self.log(f"CSV chargé : {path}")
        except Exception as e:
            self.log(f"Erreur chargement CSV: {e}")
            QMessageBox.warning(self, "Erreur", f"Impossible de charger CSV: {e}")

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir CSV", str(BASE_DIR / 'data'), "CSV Files (*.csv)")
        if path:
            self.load_csv(path)

    def on_save(self):
        # sauvegarde vers le même fichier ou Save As
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer CSV", str(BASE_DIR / 'data' / 'projects_example.csv'), "CSV Files (*.csv)")
        if path:
            df = qtable_to_df(self.table)
                        # === AJOUT : validation erreur utilisateur ===
            mandatory = ["proj_id", "cost", "benefit"]
            for m in mandatory:
                if m not in df.columns:
                    QMessageBox.critical(self, "Erreur", f"Colonne obligatoire manquante : {m}")
                    return

            # vérifier numeric fields
            num_cols = ["cost", "benefit", "labour", "land", "priority", "social_score"]
            for c in num_cols:
                if c in df.columns:
                    bad = pd.to_numeric(df[c], errors="coerce").isna()
                    if bad.any():
                        QMessageBox.warning(
                            self,
                            "Erreur",
                            f"Valeurs non numériques dans colonne '{c}'."
                        )
                        return
            save_df_to_csv(df, path)
            self.log(f"CSV enregistré : {path}")

    def on_add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        # Optionnel: remplir la colonne proj_id avec Pxx automatique
        headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]
        if 'proj_id' in headers:
            cidx = headers.index('proj_id')
            # génère Pnn
            new_id = f"P{r+1:02d}"
            self.table.setItem(r, cidx, QTableWidgetItem(new_id))
        self.log("Ligne ajoutée (édition disponible)")

    def on_delete_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.log(f"Ligne {r} supprimée")
        else:
            self.log("Aucune ligne sélectionnée pour suppression")

    def on_validate(self):
        # simple validation (like ton script)
        df = qtable_to_df(self.table)
        errors = []
        if df['proj_id'].duplicated().any():
            errors.append("proj_id duplicates found")
        numeric_cols = ['cost', 'benefit']
        for c in numeric_cols:
            if c in df.columns:
                try:
                    bad = (pd.to_numeric(df[c], errors='coerce') <= 0).any()
                    if bad:
                        errors.append(f"Some values in {c} <= 0 or invalid")
                except Exception:
                    errors.append(f"Error parsing column {c}")
        if not errors:
            QMessageBox.information(self, "Validation", "Validation rapide passée")
            self.log("Validation: OK")
        else:
            QMessageBox.warning(self, "Validation", "\n".join(errors))
            self.log("Validation erreurs: " + ";".join(errors))

    # ---------- Solver ----------
    def on_solve(self):
        # récupère df depuis table (pour prendre edits)
        df = qtable_to_df(self.table)
        # paramètres simples à lire depuis inputs
        try:
            budget = float(self.budget_input.text()) if self.budget_input.text().strip() else 2000000.0
        except ValueError:
            QMessageBox.warning(self, "Erreur", "Budget invalide")
            return
        time_limit = int(self.timelimit_input.value())
        pool = int(self.pool_input.value())

        # Préparer options de ressources/dépendances/exclusive depuis df
        resource_caps = {}
        # si colonnes 'labour' ou 'land' présentes on peut demander à l'utilisateur (ici fixés)
        if 'labour' in df.columns:
            resource_caps['labour'] = 2000
        if 'land' in df.columns:
            resource_caps['land'] = 4000

        # groups_exclusive : construit automatiquement depuis exclusive_group column si présente
        groups = []
        if 'exclusive_group' in df.columns:
            for gname in df['exclusive_group'].unique():
                if gname and str(gname).strip():
                    members = df[df['exclusive_group'] == gname]['proj_id'].tolist()
                    if members:
                        groups.append(members)
        # dependencies : parse 'requires' column like (i,j) pairs
        deps = []
        if 'requires' in df.columns:
            for p, req in df.set_index('proj_id')['requires'].items():
                if isinstance(req, str) and req.strip():
                    for r in req.split(';'):
                        r = r.strip()
                        if r:
                            deps.append((r, p))

        # désactiver bouton solve, activer stop
        self.btn_solve.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log("Lancement du solver...")

        # create and start solver thread
        self.solver_thread = SolverThread(df=df,
                                          budget=budget,
                                          resource_caps=resource_caps,
                                          groups_exclusive=groups,
                                          dependencies=deps,
                                          region_min_max=None,
                                          K=None,
                                          time_limit=time_limit,
                                          pool_solutions=pool,
                                          pool_gap=0.05,
                                          multi_crit_alpha=1.0)
        self.solver_thread.finished.connect(self.on_solver_finished)
        self.solver_thread.error.connect(self.on_solver_error)
        self.solver_thread.start()
    def _auto_save_cell(self, item):
        """Sauvegarde automatique après modification d’une cellule."""
        try:
            row = item.row()
            col = item.column()
            new_val = item.text()

            df = qtable_to_df(self.table)
            colname = df.columns[col]

            # Vérification : si la colonne doit être numérique
            if colname in ["cost", "benefit", "labour", "land", "priority", "social_score"]:
                float(new_val)  # lève ValueError si invalide

            # Mise à jour DataFrame et sauvegarde
            df.at[row, colname] = new_val
            if self.df is not None:
                self.df = df

            if self.csv_path:
                df.to_csv(self.csv_path, index=False)
                self.log(f"Auto-save: colonne {colname}, ligne {row}")

        except ValueError:
            QMessageBox.warning(self, "Erreur", f"Valeur invalide dans '{colname}' : doit être numérique.")
            # Restaurer ancienne valeur
            old_df = qtable_to_df(self.table)
            item.setText(str(old_df.iloc[row, col]))

    def on_stop(self):
        # Tentative d'arrêt: pour gurobi, on peut définir un flag (non trivial),
        # ici on arrête le thread (ne garantit pas l'arrêt du solveur natif)
        if self.solver_thread and self.solver_thread.isRunning():
            # arrête le thread proprement si possible
            try:
                self.solver_thread.terminate()
                self.solver_thread.wait(1000)
                self.log("Thread solver arrêté manuellement (terminate).")
            except Exception as e:
                self.log(f"Erreur arrêt thread: {e}")
        self.btn_solve.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def on_solver_finished(self, payload):
        """Handle solver completion with improved result display."""
        self.btn_solve.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        if payload.get('status') == 'ok':
            res = payload.get('result', {})
            sols = res.get('solutions', [])
            
            if sols:
                # Store all solutions for navigation
                self.pool_solutions = sols
                self.current_sol_idx = 0
                
                # Update navigation buttons
                self._update_solution_display()
                
                self.log(f" Solveur terminé. {len(sols)} solution(s) trouvée(s).")
            else:
                self.result_label.setText("⚠️ Aucune solution trouvée")
                self.log("⚠️ Aucune solution retournée par le solveur.")
                self.pool_solutions = []
                self.current_sol_idx = 0
                # Clear plot
                self.ax.clear()
                self.ax.text(0.5, 0.5, 'Aucune solution', ha='center', va='center', fontsize=12, color='#e74c3c')
                self.ax.set_xlim(0, 1)
                self.ax.set_ylim(0, 1)
                self.ax.axis('off')
                self.canvas.draw()
        else:
            status_msg = payload.get('status', 'unknown')
            self.result_label.setText(f"❌ Erreur: {status_msg}")
            self.log(f"❌ Solveur terminé avec statut: {status_msg}")
        
        self.solver_thread = None

    def _update_solution_display(self):
        """Display current solution from the pool."""
        if not self.pool_solutions:
            return
        
        if self.current_sol_idx < 0 or self.current_sol_idx >= len(self.pool_solutions):
            self.current_sol_idx = 0
        
        current = self.pool_solutions[self.current_sol_idx]
        selected = current.get('selected', [])
        obj = current.get('obj', None)
        
        # Format result label
        num_projects = len(selected)
        result_text = f" Solution {self.current_sol_idx + 1}/{len(self.pool_solutions)}\nObj: {obj:.2f} | Projets: {num_projects}"
        self.result_label.setText(result_text)
        
        # Update solution list
        self.solution_list.clear()
        self.solution_list.appendPlainText("=== Projets sélectionnés ===")
        for p in selected:
            self.solution_list.appendPlainText(f"- {p}")
        self.solution_list.appendPlainText(f"\nObjectif total : {obj:.2f}")
        
        # Update solution counter
        self.sol_counter_label.setText(f"Sol: {self.current_sol_idx + 1}/{len(self.pool_solutions)}")
        
        # Enable/disable navigation buttons
        self.btn_prev_sol.setEnabled(self.current_sol_idx > 0)
        self.btn_next_sol.setEnabled(self.current_sol_idx < len(self.pool_solutions) - 1)
        
        # Update plot
        self.plot_selection(selected)
        
        # Store last result
        self.last_solution = current

    def on_prev_solution(self):
        """Navigate to previous solution in pool."""
        if self.current_sol_idx > 0:
            self.current_sol_idx -= 1
            self._update_solution_display()

    def on_next_solution(self):
        """Navigate to next solution in pool."""
        if self.current_sol_idx < len(self.pool_solutions) - 1:
            self.current_sol_idx += 1
            self._update_solution_display()

    def on_solver_error(self, errstr):
        self.btn_solve.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.critical(self, "Solver error", errstr)
        self.log("Solver error: " + errstr)
        self.solver_thread = None

    def plot_selection(self, selected):
        """Plot selected projects with improved aesthetics."""
        self.ax.clear()
        
        if not selected:
            self.ax.text(0.5, 0.5, 'Aucune sélection', ha='center', va='center', 
                        fontsize=12, color='#95a5a6')
            self.ax.set_xlim(0, 1)
            self.ax.set_ylim(0, 1)
            self.ax.axis('off')
        else:
            # Essayer d'abord un graphique par région
            df_sel = self.df[self.df['proj_id'].isin(selected)] if 'proj_id' in self.df.columns else pd.DataFrame()
            
            if not df_sel.empty and 'region' in df_sel.columns:
                counts = df_sel['region'].value_counts().sort_values(ascending=True)
                counts.plot(kind='barh', ax=self.ax, color='#3498db', edgecolor='#2c3e50', linewidth=1.5)
                self.ax.set_xlabel('Nombre de projets', fontsize=10, fontweight='bold')
                self.ax.set_ylabel('Région', fontsize=10, fontweight='bold')
                self.ax.set_title('Répartition régionale (sélection)', fontsize=11, fontweight='bold', color='#2c3e50')
                self.ax.grid(axis='x', alpha=0.3, linestyle='--')
            elif not df_sel.empty and 'benefit' in df_sel.columns:
                # Graphique des bénéfices par projet
                benefits = df_sel.set_index('proj_id')['benefit'].sort_values(ascending=True)
                benefits.plot(kind='barh', ax=self.ax, color='#27ae60', edgecolor='#2c3e50', linewidth=1.5)
                self.ax.set_xlabel('Bénéfice', fontsize=10, fontweight='bold')
                self.ax.set_ylabel('Projet', fontsize=10, fontweight='bold')
                self.ax.set_title('Bénéfices des projets sélectionnés', fontsize=11, fontweight='bold', color='#2c3e50')
                self.ax.grid(axis='x', alpha=0.3, linestyle='--')
            else:
                self.ax.text(0.5, 0.5, 'Aucune donnée à tracer', ha='center', va='center',
                            fontsize=12, color='#95a5a6')
                self.ax.set_xlim(0, 1)
                self.ax.set_ylim(0, 1)
                self.ax.axis('off')
        
        self.fig.tight_layout()
        self.canvas.draw()

    def on_show_selected(self):
        if hasattr(self, 'last_solution') and self.last_solution:
            sel = self.last_solution.get('selected', [])
            QMessageBox.information(self, "Dernière sélection", ", ".join(sel) if sel else "Aucune")
        else:
            QMessageBox.information(self, "Dernière sélection", "Aucune exécution encore réalisée")

    # def log(self, text):
    #     prev = self.log_label.text()
    #     new = f"{prev}\n{text}" if prev else text
    #     # limiter la taille du log
    #     if len(new) > 5000:
    #         new = new[-5000:]
    #     self.log_label.setText(new)
    def log(self, text):
        """Write a message in the log_widget safely."""
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {text}"

        try:
            self.log_widget.appendPlainText(line)

            # limiter la taille
            content = self.log_widget.toPlainText()
            if len(content) > 20000:
                trimmed = content[-15000:]
                self.log_widget.setPlainText(trimmed)

            # autoscroll
            bar = self.log_widget.verticalScrollBar()
            bar.setValue(bar.maximum())

        except Exception:
            print(line)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
