import pandas as pd

path = 'data/projects_example.csv'
df = pd.read_csv(path, dtype={'proj_id':str})
print("Loaded", len(df), "projects")
print(df.head())

# Basic validation
errors = []
if df['proj_id'].duplicated().any():
    errors.append("proj_id duplicates found")
if (df['cost'] <= 0).any():
    errors.append("Some costs <= 0")
if (df['benefit'] <= 0).any():
    errors.append("Some benefits <= 0")
if not errors:
    print("Basic validation passed")
else:
    print("Validation errors:", errors)

# Example: list projects that require missing prereqs
reqs = df['requires'].fillna('').astype(str)
for idx, r in reqs.items():
    if r.strip():
        for rid in r.split(';'):
            rid = rid.strip()
            if rid and rid not in df['proj_id'].values:
                print(f"Warning: project {df.loc[idx,'proj_id']} requires missing project {rid}")
