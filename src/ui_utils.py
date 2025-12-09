# src/ui_utils.py
import pandas as pd
from PyQt5.QtWidgets import QTableWidgetItem

def df_to_qtable(table_widget, df):
    """
    Remplit un QTableWidget à partir d'un pandas DataFrame.
    Le QTableWidget est redimensionné pour correspondre aux colonnes/rows du df.
    """
    table_widget.clear()
    table_widget.setColumnCount(len(df.columns))
    table_widget.setRowCount(len(df.index))
    table_widget.setHorizontalHeaderLabels(list(df.columns))

    for i, row in df.iterrows():
        for j, col in enumerate(df.columns):
            val = row[col]
            item = QTableWidgetItem("" if pd.isna(val) else str(val))
            table_widget.setItem(i, j, item)
    table_widget.resizeColumnsToContents()

def qtable_to_df(table_widget):
    """
    Lit un QTableWidget et retourne un pandas DataFrame.
    Les en-têtes de colonne sont lus depuis le widget.
    """
    n_rows = table_widget.rowCount()
    n_cols = table_widget.columnCount()
    headers = [table_widget.horizontalHeaderItem(c).text() for c in range(n_cols)]
    data = []
    for r in range(n_rows):
        row = []
        # si row vide (tous items None), on ajoute une ligne vide
        empty = True
        for c in range(n_cols):
            it = table_widget.item(r, c)
            val = "" if it is None else it.text()
            if val != "":
                empty = False
            row.append(val)
        # on garde les lignes même vides (contrôle par UI si nécessaire)
        data.append(row)
    df = pd.DataFrame(data, columns=headers)
    # Essaie de convertir les colonnes numériques classiques en numériques quand possible
    for col in df.columns:
        # On tente conversion si valeur non vide et ressemble à nombre
        try:
            df[col] = pd.to_numeric(df[col], errors='ignore')
        except Exception:
            pass
    return df

def load_csv_to_df(path):
    df = pd.read_csv(path, dtype={'proj_id':str})
    df.fillna('', inplace=True)
    return df

def save_df_to_csv(df, path):
    df.to_csv(path, index=False)
