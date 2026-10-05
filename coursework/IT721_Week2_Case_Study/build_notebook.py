"""Builds Week2_Case_Study_Tamara_Dinneen.ipynb (IT721 Week 2 Case Study).

Run:  python build_notebook.py   -> writes the un-executed notebook next to this file.
"""
import json
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).parent
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text.strip("\n")))


def code(text):
    cells.append(nbf.v4.new_code_cell(text.strip("\n")))


# ----------------------------------------------------------------------------
# Title
# ----------------------------------------------------------------------------
md(r"""
# Week 2 Case Study: Neural Networks & Advanced Backpropagation
## Wine Quality Assessment — Gradient Flow, Optimisation and Regularisation

**Student:** Tamara Dinneen
**Course:** IT721 Applied Research Topics in Deep Learning
**Dataset:** Red Wine Quality (Cortez et al., 2009) — Kaggle `uciml/red-wine-quality-cortez-et-al-2009`

| Part | Rubric item | Points |
|---|---|---|
| 1 | Data Preparation & Feature Engineering | 8 |
| 2 | Gradient Flow Analysis | 12 |
| 3 | Advanced Optimization Techniques | 15 |
| 4 | Regularization & Generalization | 6 |
| 5 | Written Analysis & Reflection | 4 |

**Prediction task.** Following the dataset documentation (scores of 7 or above are classed as *good*), the model is a binary classifier for `good = quality >= 7`. Only about 14% of wines are "good", so the main metrics are ones that hold up under class imbalance: **ROC-AUC** and **PR-AUC (average precision)**, plus F1, balanced accuracy and Matthews correlation coefficient (MCC) at a decision threshold.

**Protocol.** All tuning decisions use the **validation** split. The **test** split is used **once**, in the final evaluation (Section 4.6). Every comparison is repeated over several random seeds and reported as mean ± std, because on a dataset this small a single run can mislead.

> Runtime: about 45–60 minutes for *Run all* on a Colab CPU runtime (a GPU gives little speed-up for networks this small). Set `FAST = True` in Section 0 for a quick run with one seed and fewer epochs.
""")

# ----------------------------------------------------------------------------
# 0. Setup
# ----------------------------------------------------------------------------
md(r"""
## 0. Environment Setup & Reproducibility
""")

code(r"""
import os, time, math, warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

import tensorflow as tf
import keras
from keras import layers, regularizers

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import PowerTransformer, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (roc_auc_score, average_precision_score, f1_score, balanced_accuracy_score,
                             matthews_corrcoef, confusion_matrix, classification_report, roc_curve,
                             precision_recall_curve, brier_score_loss, log_loss, precision_score, recall_score)
from sklearn.calibration import calibration_curve
from sklearn.utils.class_weight import compute_class_weight

FAST = False                      # True = quick smoke run (1 seed, fewer epochs)
SEED = 42
SEEDS = [42] if FAST else [42, 7, 2024]
EPOCH_SCALE = 0.3 if FAST else 1.0
def E(n):                          # scale epoch budgets in FAST mode
    return max(5, int(n * EPOCH_SCALE))

keras.utils.set_random_seed(SEED)
try:
    tf.config.experimental.enable_op_determinism()
except Exception as e:
    print('Op determinism not available:', e)

pd.set_option('display.float_format', lambda v: f'{v:,.4f}')
pd.set_option('display.max_columns', 50)
sns.set_theme(style='whitegrid', context='notebook')
plt.rcParams.update({'figure.dpi': 85, 'axes.titleweight': 'bold'})
PALETTE = sns.color_palette('tab10')

print('TensorFlow', tf.__version__, '| Keras', keras.__version__, '| GPU:', tf.config.list_physical_devices('GPU'))
""")

# ----------------------------------------------------------------------------
# PART 1
# ----------------------------------------------------------------------------
md(r"""
---
# Part 1: Data Preparation & Feature Engineering (8 points)

## 1.1 Load the dataset
The loader checks for a local copy first (the Colab working directory, or the `DBA/IT 721 DL/Assignment2` folder in Google Drive). If none is found it downloads a public mirror of the same Kaggle/UCI file (1,599 red wines, 11 physicochemical inputs and a sensory `quality` score from 0 to 10).
""")

code(r"""
DATA_URL = 'https://raw.githubusercontent.com/plotly/datasets/master/winequality-red.csv'
CANDIDATES = ['winequality-red.csv', '/content/winequality-red.csv',
              '/content/drive/MyDrive/DBA/IT 721 DL/Assignment2/winequality-red.csv']
try:                                   # mount Google Drive when running in Colab
    from google.colab import drive
    drive.mount('/content/drive')
except Exception:
    pass

path = next((p for p in CANDIDATES if os.path.exists(p)), None)
source = path if path else DATA_URL
df_raw = pd.read_csv(source, encoding='utf-8-sig')
if df_raw.shape[1] == 1:               # the UCI original uses ';' as separator
    df_raw = pd.read_csv(source, sep=';', encoding='utf-8-sig')
df_raw.columns = [c.strip() for c in df_raw.columns]

print('Loaded from:', source)
print('Shape:', df_raw.shape)
df_raw.head()
""")

code(r"""
print('Data types:'); print(df_raw.dtypes.value_counts().to_string())
print('\nMissing values per column:', int(df_raw.isna().sum().sum()))
n_dup = int(df_raw.duplicated().sum())
print(f'Exact duplicate rows: {n_dup} ({n_dup/len(df_raw):.1%})')

fig, ax = plt.subplots(1, 2, figsize=(12, 3.8))
q = df_raw['quality'].value_counts().sort_index()
ax[0].bar(q.index, q.values, color=[PALETTE[3] if i >= 7 else PALETTE[0] for i in q.index])
for i, v in zip(q.index, q.values):
    ax[0].text(i, v + 10, str(v), ha='center')
ax[0].set(title='Quality score distribution (red = "good", >= 7)', xlabel='quality', ylabel='count')
good_share = (df_raw['quality'] >= 7).mean()
ax[1].pie([1 - good_share, good_share], labels=['not good (<7)', 'good (>=7)'], autopct='%1.1f%%',
          colors=[PALETTE[0], PALETTE[3]], startangle=90)
ax[1].set_title('Binary target balance')
plt.tight_layout(); plt.show()
""")

md(r"""
**Observations.** The data has no missing values and all 12 columns are numeric. Two points shape the rest of the pipeline:
1. **Duplicates.** About 15% of rows are exact duplicates (the same wine recorded more than once). If they are left in, copies of the same wine can land in both train and test, which leaks information and inflates test scores. They are removed **before** splitting (Section 1.4).
2. **Imbalance and ordinal target.** Scores 5 and 6 make up over 80% of the data, and only about 14% are "good". This calls for stratified splits, class weighting, and imbalance-aware metrics.

## 1.2 Comprehensive statistical analysis of feature distributions
""")

code(r"""
FEATURES = [c for c in df_raw.columns if c != 'quality']

def iqr_outliers(s):
    q1, q3 = s.quantile([.25, .75]); iqr = q3 - q1
    return int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())

stat_tbl = df_raw[FEATURES].describe().T
stat_tbl['cv'] = stat_tbl['std'] / stat_tbl['mean']
stat_tbl['skew'] = df_raw[FEATURES].skew()
stat_tbl['kurtosis'] = df_raw[FEATURES].kurt()
stat_tbl['normaltest_p'] = [stats.normaltest(df_raw[c])[1] for c in FEATURES]   # D'Agostino-Pearson
stat_tbl['iqr_outliers'] = [iqr_outliers(df_raw[c]) for c in FEATURES]
stat_tbl['outlier_%'] = 100 * stat_tbl['iqr_outliers'] / len(df_raw)
stat_tbl.sort_values('skew', ascending=False)
""")

code(r"""
df_plot = df_raw.assign(good=np.where(df_raw['quality'] >= 7, 'good', 'not good'))
fig, axes = plt.subplots(3, 4, figsize=(16, 10))
for ax, c in zip(axes.ravel(), FEATURES):
    sns.histplot(data=df_plot, x=c, hue='good', stat='density', common_norm=False, kde=True,
                 palette={'good': PALETTE[3], 'not good': PALETTE[0]}, ax=ax, alpha=.35, legend=(c == FEATURES[0]))
    ax.set_title(f'{c}\nskew={df_raw[c].skew():.2f}', fontsize=10); ax.set_xlabel('')
axes.ravel()[-1].axis('off')
plt.suptitle('Feature distributions by class (density, class-normalised)', y=1.0, fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
""")

code(r"""
fig, axes = plt.subplots(3, 4, figsize=(16, 10))
for ax, c in zip(axes.ravel(), FEATURES):
    sns.boxplot(data=df_raw, x='quality', y=c, ax=ax, color=PALETTE[0], fliersize=2)
    ax.set_title(c, fontsize=10); ax.set_ylabel('')
axes.ravel()[-1].axis('off')
plt.suptitle('Feature vs quality score (box plots; dots = IQR outliers)', y=1.0, fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
""")

code(r"""
fig, ax = plt.subplots(1, 2, figsize=(17, 6.5), gridspec_kw={'width_ratios': [1.35, 1]})
corr = df_raw.corr(method='spearman')
mask = np.triu(np.ones_like(corr, dtype=bool), 1)
sns.heatmap(corr, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r', center=0, vmin=-1, vmax=1,
            ax=ax[0], annot_kws={'size': 8}, cbar_kws={'shrink': .7})
ax[0].set_title('Spearman rank correlation matrix')
qc = corr['quality'].drop('quality').sort_values()
ax[1].barh(qc.index, qc.values, color=[PALETTE[3] if v > 0 else PALETTE[0] for v in qc.values])
ax[1].axvline(0, color='k', lw=.8); ax[1].set_title('Spearman correlation with quality')
plt.tight_layout(); plt.show()
""")

code(r"""
# Non-parametric group tests (features are non-normal, so t-tests/ANOVA assumptions fail)
good_mask = df_raw['quality'] >= 7
rows = []
for c in FEATURES:
    a, b = df_raw.loc[good_mask, c], df_raw.loc[~good_mask, c]
    u, p_mw = stats.mannwhitneyu(a, b, alternative='two-sided')
    rbc = 1 - 2 * u / (len(a) * len(b))                    # rank-biserial effect size
    h, p_kw = stats.kruskal(*[g[c].values for _, g in df_raw.groupby('quality')])
    rows.append({'feature': c, 'median_good': a.median(), 'median_not_good': b.median(),
                 'mannwhitney_p': p_mw, 'rank_biserial_r': -rbc, 'kruskal_H(all scores)': h, 'kruskal_p': p_kw})
tests = pd.DataFrame(rows).set_index('feature').sort_values('rank_biserial_r', key=np.abs, ascending=False)
tests
""")

md(r"""
**Statistical findings**
- **Non-normality.** Every feature rejects normality under the D'Agostino–Pearson test (p ≪ 0.05). `chlorides`, `residual sugar`, `sulphates` and `total sulfur dioxide` are strongly right-skewed (skew > 1.5) with heavy tails (kurtosis up to about 40 for chlorides). Neural networks train best on roughly symmetric inputs with zero mean and unit variance, so a **power transform** (Yeo–Johnson) is used rather than plain standardisation, and robust, rank-based statistics are used here.
- **Outliers.** IQR outliers affect up to about 7% of rows (chlorides, residual sugar, sulphates). They look like real wines, such as sweet or high-sulphate styles, rather than recording errors, so they are **kept** and their influence is reduced with the power transform instead of being deleted.
- **Signal.** `alcohol` has the strongest monotone association with quality (Spearman ≈ +0.48), followed by `volatile acidity` (≈ −0.38, the vinegar character of acetic acid), `sulphates` (+) and `citric acid` (+). The Mann–Whitney tests confirm these features separate *good* from *not good* wines with medium-to-large effect sizes. `residual sugar`, `free sulfur dioxide` and `pH` carry almost no univariate signal.
- **Multicollinearity.** `fixed acidity`, `citric acid`, `density` and `pH` are strongly inter-correlated (|ρ| ≈ 0.5–0.7), as acid chemistry would predict. This motivates the redundancy filter in feature selection.

## 1.3 Domain-driven feature engineering
Each engineered feature is a **row-wise** function of that wine's own measurements, so it cannot leak information between splits:

| Feature | Formula | Domain rationale |
|---|---|---|
| `total_acidity` | fixed + volatile + citric | overall perceived sourness/freshness |
| `fixed_to_volatile` | fixed / volatile | "good" acids (tartaric) vs spoilage acid (acetic) |
| `free_so2_ratio` | free SO₂ / total SO₂ | share of SO₂ that is active vs bound |
| `molecular_so2` | free SO₂ / (1 + 10^(pH − 1.81)) | the antimicrobial molecular form of SO₂ depends on pH (pKa ≈ 1.81); winemakers target about 0.5–0.8 mg/L |
| `bound_so2` | total − free SO₂ | bound to acetaldehyde/sugars; an oxidation marker |
| `alcohol_x_sulphates` | alcohol × sulphates | the two strongest positive signals; a ripeness × preservation interaction |
| `sugar_to_alcohol` | residual sugar / alcohol | fermentation completeness / sweetness balance |
| `acid_to_alcohol` | total acidity / alcohol | the structural balance between acid and alcohol |
| `alcohol_band` *(categorical)* | low < 10% ≤ medium < 11.5% ≤ high | a wine-trade style band, used to demonstrate categorical encoding |
""")

code(r"""
def engineer_features(d):
    d = d.copy()
    d['total_acidity'] = d['fixed acidity'] + d['volatile acidity'] + d['citric acid']
    d['fixed_to_volatile'] = d['fixed acidity'] / d['volatile acidity']
    d['free_so2_ratio'] = d['free sulfur dioxide'] / d['total sulfur dioxide']
    d['molecular_so2'] = d['free sulfur dioxide'] / (1 + 10 ** (d['pH'] - 1.81))
    d['bound_so2'] = d['total sulfur dioxide'] - d['free sulfur dioxide']
    d['alcohol_x_sulphates'] = d['alcohol'] * d['sulphates']
    d['sugar_to_alcohol'] = d['residual sugar'] / d['alcohol']
    d['acid_to_alcohol'] = d['total_acidity'] / d['alcohol']
    d['alcohol_band'] = pd.cut(d['alcohol'], bins=[0, 10, 11.5, 100], right=False,
                               labels=['low', 'medium', 'high']).astype(str)
    return d

# Remove exact duplicates BEFORE splitting to prevent train/test leakage
df = df_raw.drop_duplicates().reset_index(drop=True)
df['good'] = (df['quality'] >= 7).astype(int)
df = engineer_features(df)
print(f'Rows after de-duplication: {len(df)} (removed {len(df_raw) - len(df)})')
print(f'Positive ("good") rate after de-duplication: {df.good.mean():.3f}')

ENG = ['total_acidity', 'fixed_to_volatile', 'free_so2_ratio', 'molecular_so2', 'bound_so2',
       'alcohol_x_sulphates', 'sugar_to_alcohol', 'acid_to_alcohol']
NUMERIC = FEATURES + ENG
CATEGORICAL = ['alcohol_band']

# Quick check of engineered-feature signal (Spearman with quality, univariate AUC for 'good')
sig = pd.DataFrame({
    'spearman_quality': [stats.spearmanr(df[c], df['quality'])[0] for c in NUMERIC],
    'univariate_auc_good': [max(roc_auc_score(df['good'], df[c]), 1 - roc_auc_score(df['good'], df[c])) for c in NUMERIC],
    'type': ['original'] * len(FEATURES) + ['engineered'] * len(ENG)}, index=NUMERIC)
display(sig.sort_values('univariate_auc_good', ascending=False).head(12))
print(pd.crosstab(df['alcohol_band'], df['good'], normalize='index').round(3))
""")

md(r"""
`alcohol_x_sulphates` is **more predictive than either parent feature alone** (it ranks first by univariate AUC), and `fixed_to_volatile` beats `volatile acidity`. Both support the domain reasoning. The `alcohol_band` crosstab shows a steep gradient: high-alcohol wines are far more often "good". Section 4.7 comes back to this as a possible source of bias.

## 1.4 Stratified train / validation / test split (70 / 15 / 15)
The split is stratified on the **original quality score**, not just the binary label. This keeps both the "good" rate and the full 3–8 score mix (including the rare 3s and 8s) the same in every split.
""")

code(r"""
idx = np.arange(len(df))
try:
    tr_idx, tmp_idx = train_test_split(idx, test_size=0.30, stratify=df['quality'], random_state=SEED)
    va_idx, te_idx = train_test_split(tmp_idx, test_size=0.50, stratify=df['quality'].iloc[tmp_idx], random_state=SEED)
    strat_on = 'quality score'
except ValueError:                      # fallback if a score class is too rare
    tr_idx, tmp_idx = train_test_split(idx, test_size=0.30, stratify=df['good'], random_state=SEED)
    va_idx, te_idx = train_test_split(tmp_idx, test_size=0.50, stratify=df['good'].iloc[tmp_idx], random_state=SEED)
    strat_on = 'binary label'

df_tr, df_va, df_te = df.iloc[tr_idx], df.iloc[va_idx], df.iloc[te_idx]
split_tbl = pd.DataFrame({name: {'n': len(d), 'good_rate': d['good'].mean(),
                                  **{f'q={k}': (d['quality'] == k).mean() for k in sorted(df.quality.unique())}}
                          for name, d in [('train', df_tr), ('validation', df_va), ('test', df_te), ('all', df)]}).T
print('Stratified on:', strat_on)
split_tbl
""")

md(r"""
## 1.5 Advanced preprocessing: transformation, scaling, encoding (fit on training data only)
- **Numeric:** `PowerTransformer(method='yeo-johnson', standardize=True)`. This removes skew, then centres and scales each feature, and handles zeros (e.g. `citric acid = 0`), which a log or Box–Cox transform cannot.
- **Categorical:** `OneHotEncoder(handle_unknown='ignore')` for `alcohol_band`.
- **Target:** already encoded as an integer 0/1 label.
- Every transformer is fit on **train only** and then applied to validation and test, so no distribution information leaks from the held-out data.
""")

code(r"""
def make_preprocessor(numeric, categorical):
    return ColumnTransformer([
        ('num', PowerTransformer(method='yeo-johnson', standardize=True), numeric),
        ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical)])

pre_full = make_preprocessor(NUMERIC, CATEGORICAL).fit(df_tr)
feat_names_full = NUMERIC + [f'alcohol_band_{c}' for c in pre_full.named_transformers_['cat'].categories_[0]]
Xtr_full = pd.DataFrame(pre_full.transform(df_tr), columns=feat_names_full, index=df_tr.index)
Xva_full = pd.DataFrame(pre_full.transform(df_va), columns=feat_names_full, index=df_va.index)
y_train, y_val, y_test = df_tr['good'].values, df_va['good'].values, df_te['good'].values

skew_cmp = pd.DataFrame({'skew_before': df_tr[NUMERIC].skew(), 'skew_after': Xtr_full[NUMERIC].skew(),
                         'mean_after': Xtr_full[NUMERIC].mean(), 'std_after': Xtr_full[NUMERIC].std()})
fig, ax = plt.subplots(figsize=(13, 4))
skew_cmp[['skew_before', 'skew_after']].plot.bar(ax=ax, color=[PALETTE[1], PALETTE[2]])
ax.axhline(0, color='k', lw=.8); ax.set_title('Skewness before vs after Yeo-Johnson (training set)')
plt.xticks(rotation=60, ha='right'); plt.tight_layout(); plt.show()
skew_cmp.round(3).T
""")

md(r"""
## 1.6 Feature selection
A three-stage, training-set-only procedure:
1. **Relevance:** mutual information between each feature and the target. This captures non-linear dependence.
2. **Redundancy filter:** for every pair with |Pearson r| > 0.85, drop the member with the lower mutual information.
3. **Embedded check:** an L1-penalised (lasso) logistic regression. A feature is kept if it survives the redundancy filter **and** shows relevance (MI ≥ 0.01 **or** a non-zero L1 coefficient).

The choice is then checked with a logistic-regression baseline on the validation set, and multicollinearity is measured with the variance inflation factor (VIF).
""")

code(r"""
mi = pd.Series(mutual_info_classif(Xtr_full, y_train, random_state=SEED,
                                   discrete_features=[c.startswith('alcohol_band') for c in feat_names_full]),
               index=feat_names_full)
lasso = LogisticRegression(penalty='l1', solver='liblinear', C=0.1, class_weight='balanced',
                           random_state=SEED).fit(Xtr_full, y_train)
l1_coef = pd.Series(lasso.coef_.ravel(), index=feat_names_full)

corr_abs = Xtr_full.corr().abs()
dropped_redundant = set()
for i, a in enumerate(feat_names_full):
    for b in feat_names_full[i + 1:]:
        if corr_abs.loc[a, b] > 0.85 and a not in dropped_redundant and b not in dropped_redundant:
            dropped_redundant.add(a if mi[a] < mi[b] else b)

SELECTED = [f for f in feat_names_full
            if f not in dropped_redundant and (mi[f] >= 0.01 or abs(l1_coef[f]) > 1e-6)]

def vif(X):
    inv = np.linalg.pinv(np.corrcoef(X, rowvar=False))
    return pd.Series(np.diag(inv), index=X.columns)

sel_tbl = pd.DataFrame({'mutual_info': mi, 'l1_coef': l1_coef,
                        'redundant_dropped': [f in dropped_redundant for f in feat_names_full],
                        'selected': [f in SELECTED for f in feat_names_full]})
num_cols_full = [c for c in feat_names_full if not c.startswith('alcohol_band')]
sel_tbl['VIF_all'] = vif(Xtr_full[num_cols_full]).reindex(feat_names_full)
num_sel = [c for c in SELECTED if not c.startswith('alcohol_band')]
sel_tbl['VIF_selected'] = vif(Xtr_full[num_sel]).reindex(feat_names_full)
display(sel_tbl.sort_values('mutual_info', ascending=False))
print(f'Selected {len(SELECTED)} of {len(feat_names_full)} features:', SELECTED)
print('Dropped as redundant:', sorted(dropped_redundant))
print('Dropped as irrelevant:', sorted(set(feat_names_full) - set(SELECTED) - dropped_redundant))
""")

code(r"""
fig, ax = plt.subplots(figsize=(13, 4))
o = sel_tbl.sort_values('mutual_info', ascending=False)
ax.bar(o.index, o['mutual_info'], color=[PALETTE[2] if s else PALETTE[7] for s in o['selected']])
ax.set_title('Mutual information with target (green = selected, grey = dropped)')
plt.xticks(rotation=60, ha='right'); plt.tight_layout(); plt.show()

def lr_val_auc(cols):
    m = LogisticRegression(max_iter=2000, class_weight='balanced').fit(Xtr_full[cols], y_train)
    return roc_auc_score(y_val, m.predict_proba(Xva_full[cols])[:, 1])
print(f'Logistic regression validation ROC-AUC  | original 11 features: {lr_val_auc(FEATURES):.4f}'
      f' | all {len(feat_names_full)} features: {lr_val_auc(feat_names_full):.4f}'
      f' | selected {len(SELECTED)}: {lr_val_auc(SELECTED):.4f}')
""")

code(r"""
# Final model-ready matrices (float32 for TensorFlow)
X_train = Xtr_full[SELECTED].values.astype('float32')
X_val = Xva_full[SELECTED].values.astype('float32')
X_test = pd.DataFrame(pre_full.transform(df_te), columns=feat_names_full)[SELECTED].values.astype('float32')
N_FEAT = X_train.shape[1]

cw = compute_class_weight('balanced', classes=np.array([0, 1]), y=y_train)
CLASS_WEIGHT = {0: float(cw[0]), 1: float(cw[1])}
print('X_train', X_train.shape, '| X_val', X_val.shape, '| X_test', X_test.shape)
print('Class weights (balanced):', {k: round(v, 3) for k, v in CLASS_WEIGHT.items()})

# Classical reference baselines (validation only)
base_rows = {}
for name, mdl in [('Logistic regression', LogisticRegression(max_iter=2000, class_weight='balanced')),
                  ('Random forest (500 trees)', RandomForestClassifier(n_estimators=500, min_samples_leaf=2,
                                                class_weight='balanced_subsample', random_state=SEED, n_jobs=-1))]:
    mdl.fit(X_train, y_train); p = mdl.predict_proba(X_val)[:, 1]
    base_rows[name] = {'val_roc_auc': roc_auc_score(y_val, p), 'val_pr_auc': average_precision_score(y_val, p)}
BASELINES = pd.DataFrame(base_rows).T
BASELINES
""")

md(r"""
**Part 1 summary.** After de-duplication there are 1,359 unique wines, split 70/15/15 with stratification on the quality score. The skewed features are power-transformed, the categorical band is one-hot encoded, and selection keeps a compact, low-VIF feature set. The redundancy filter removes engineered features that duplicate their parents (such as `total_acidity` vs `fixed acidity`) and keeps the more informative member of each pair. The classical baselines give the neural networks a target to beat; a random forest scores roughly 0.88–0.90 validation AUC on this data.

---
# Part 2: Gradient Flow Analysis (12 points)

## 2.1 Model builder and a custom gradient-monitoring callback
`build_mlp` is a configurable multilayer perceptron. Each hidden block is `Dense → [BatchNorm | LayerNorm] → Activation → [Dropout]`. Because the activation is a separate named layer, its outputs can be probed directly.

`GradientMonitor` is a **custom Keras callback**. Before training and at the end of every epoch it runs a forward and backward pass with `tf.GradientTape` on a fixed probe set (the whole training set). It records the **L2 norm of ∂L/∂W for every Dense kernel**, from layer 1 (nearest the input) to the output layer. Measuring on a fixed probe set makes the epochs comparable: mini-batch noise does not affect the measurement.
""")

code(r"""
def make_activation(name, idx):
    if name == 'relu':        return layers.ReLU(name=f'act_{idx}')
    if name == 'leaky_relu':  return layers.LeakyReLU(negative_slope=0.1, name=f'act_{idx}')
    if name == 'elu':         return layers.ELU(alpha=1.0, name=f'act_{idx}')
    return layers.Activation(name, name=f'act_{idx}')     # swish, selu, tanh, sigmoid, ...

def get_initializer(init):
    if isinstance(init, str):
        return keras.initializers.get(init)
    return init()          # factory -> fresh initializer per layer (avoids identical seeded weights)

def make_regularizer(reg):
    if reg is None:          return None
    kind, *vals = reg
    if kind == 'l1':         return regularizers.L1(vals[0])
    if kind == 'l2':         return regularizers.L2(vals[0])
    if kind == 'l1l2':       return regularizers.L1L2(l1=vals[0], l2=vals[1])
    raise ValueError(kind)

def dropout_here(i, depth, positions):
    if positions == 'all':    return True
    if positions == 'early':  return i < depth // 2
    if positions == 'late':   return i >= depth // 2
    if positions == 'none':   return False
    raise ValueError(positions)

def build_mlp(depth=4, width=64, activation='relu', init='he_normal', norm=None, dropout=0.0,
              dropout_positions='all', input_dropout=0.0, reg=None, n_features=None, name='mlp'):
    inp = keras.Input((n_features or N_FEAT,), name='features')
    x = layers.Dropout(input_dropout, name='input_dropout')(inp) if input_dropout else inp
    for i in range(1, depth + 1):
        x = layers.Dense(width, kernel_initializer=get_initializer(init), kernel_regularizer=make_regularizer(reg),
                         use_bias=(norm != 'batch'), name=f'dense_{i}')(x)
        if norm == 'batch':   x = layers.BatchNormalization(name=f'bn_{i}')(x)
        elif norm == 'layer': x = layers.LayerNormalization(name=f'ln_{i}')(x)
        x = make_activation(activation, i)(x)
        if dropout > 0 and dropout_here(i - 1, depth, dropout_positions):
            x = layers.Dropout(dropout, name=f'dropout_{i}')(x)
    out = layers.Dense(1, activation='sigmoid', kernel_initializer='glorot_uniform', name='output')(x)
    return keras.Model(inp, out, name=name)


class GradientMonitor(keras.callbacks.Callback):
    # Records per-layer L2 norms of dLoss/dKernel on a fixed probe set, before training and after each epoch.
    def __init__(self, X, y, max_samples=2048):
        super().__init__()
        self.X = tf.constant(X[:max_samples])
        self.y = tf.constant(np.asarray(y[:max_samples], dtype='float32').reshape(-1, 1))
        self.loss_fn = keras.losses.BinaryCrossentropy()
        self.records, self.layer_names = [], None

    def _measure(self):
        dense = [l for l in self.model.layers if isinstance(l, layers.Dense)]
        self.layer_names = [l.name for l in dense]
        kernels = [l.kernel for l in dense]
        with tf.GradientTape() as tape:
            loss = self.loss_fn(self.y, self.model(self.X, training=True))
        grads = tape.gradient(loss, kernels)
        self.records.append([float(tf.norm(g)) if g is not None else np.nan for g in grads])

    def on_train_begin(self, logs=None):  self._measure()
    def on_epoch_end(self, epoch, logs=None): self._measure()

    def frame(self):   # rows = epoch (0 = initialisation), columns = layers
        return pd.DataFrame(self.records, columns=self.layer_names)


class LRLogger(keras.callbacks.Callback):
    def on_train_begin(self, logs=None): self.lrs = []
    def on_epoch_end(self, epoch, logs=None):
        self.lrs.append(float(np.asarray(self.model.optimizer.learning_rate)))


def evaluate(model, X, y, thr=0.5):
    p = np.clip(model.predict(X, verbose=0).ravel(), 1e-7, 1 - 1e-7)
    if not np.all(np.isfinite(p)):
        return dict(roc_auc=np.nan, pr_auc=np.nan, f1=np.nan, bal_acc=np.nan, mcc=np.nan, log_loss=np.nan)
    yhat = (p >= thr).astype(int)
    return dict(roc_auc=roc_auc_score(y, p), pr_auc=average_precision_score(y, p), f1=f1_score(y, yhat, zero_division=0),
                bal_acc=balanced_accuracy_score(y, yhat), mcc=matthews_corrcoef(y, yhat), log_loss=log_loss(y, p))

METRICS = lambda: [keras.metrics.AUC(name='auc'), keras.metrics.AUC(curve='PR', name='pr_auc')]

m = build_mlp(depth=3); m.summary()
""")

md(r"""
## 2.2 Experiment design — depths 3, 6, 9 and 12
Depth here means the number of hidden layers (width 64). Every depth is trained under three regimes chosen to show the three gradient pathologies:

| Regime | Activation | Initialisation | Expected behaviour |
|---|---|---|---|
| A. Classic | sigmoid | Glorot/Xavier uniform | **vanishing** — σ′(z) ≤ 0.25, so the gradient shrinks by at least 4× per layer |
| B. Modern | ReLU | He normal | **healthy** — derivative 1 on the active path; He scaling preserves variance |
| C. Bad init | ReLU | N(0, 0.5²) — about 2.8× He's std | **exploding** — signal variance multiplies by about 8× per layer |

All runs use plain SGD with momentum (lr = 0.01, momentum = 0.9), 60 epochs and batch size 64. Adaptive optimisers such as Adam rescale every gradient and would hide the raw gradient magnitudes this experiment is meant to show. `TerminateOnNaN` stops a run that diverges.
""")

code(r"""
DEPTHS = [3, 6, 9, 12]
EPOCHS_GRAD = E(60)
GRAD_REGIMES = {
    'A. Sigmoid + Xavier': dict(activation='sigmoid', init='glorot_uniform'),
    'B. ReLU + He': dict(activation='relu', init='he_normal'),
    'C. ReLU + N(0,0.5)': dict(activation='relu', init=lambda: keras.initializers.RandomNormal(stddev=0.5)),
}

def run_gradient_experiment(regime_kw, depth, seed=SEED, epochs=EPOCHS_GRAD, opt_fn=None, extra_kw=None):
    keras.utils.set_random_seed(seed)
    model = build_mlp(depth=depth, **regime_kw, **(extra_kw or {}))
    opt = opt_fn() if opt_fn else keras.optimizers.SGD(learning_rate=0.01, momentum=0.9)
    model.compile(optimizer=opt, loss='binary_crossentropy', metrics=METRICS())
    gm = GradientMonitor(X_train, y_train)
    hist = model.fit(X_train, y_train, validation_data=(X_val, y_val), epochs=epochs, batch_size=64,
                     class_weight=CLASS_WEIGHT, verbose=0, callbacks=[gm, keras.callbacks.TerminateOnNaN()])
    return dict(grads=gm.frame(), history=pd.DataFrame(hist.history), val=evaluate(model, X_val, y_val),
                diverged=not np.isfinite(hist.history['loss'][-1]), epochs_run=len(hist.history['loss']))

t0 = time.time()
GRAD_RESULTS = {(r, d): run_gradient_experiment(kw, d) for r, kw in GRAD_REGIMES.items() for d in DEPTHS}
print(f'{len(GRAD_RESULTS)} gradient-flow runs in {time.time() - t0:.0f}s')
""")

md(r"""
## 2.3 Visualising gradient flow through the layers
**Figure 2.3a** shows the gradient-norm profile across layers **at initialisation** (top row) and **after training** (bottom row), with one line per depth. The x-axis runs from the input side (layer 1) to the output layer, and the y-axis is log-scaled. A healthy network has a flat profile. Vanishing gradients show as a line rising toward the output (early layers receive tiny gradients); exploding gradients show as very large norms that fall toward the output.
""")

code(r"""
fig, axes = plt.subplots(2, 3, figsize=(17, 9), sharey='row')
for j, regime in enumerate(GRAD_REGIMES):
    for k, d in enumerate(DEPTHS):
        g = GRAD_RESULTS[(regime, d)]['grads']
        x = np.arange(1, g.shape[1] + 1)
        axes[0, j].semilogy(x, g.iloc[0].values, '-o', ms=4, color=PALETTE[k], label=f'{d} hidden layers')
        last = g.dropna(how='all').iloc[-1].values if g.dropna(how='all').shape[0] else g.iloc[0].values
        axes[1, j].semilogy(x, last, '-o', ms=4, color=PALETTE[k], label=f'{d} hidden layers')
    axes[0, j].set_title(f'{regime}\nat initialisation'); axes[1, j].set_title(f'{regime}\nafter training (last finite epoch)')
    for i in range(2):
        axes[i, j].set_xlabel('layer index (1 = input side, last = output layer)')
axes[0, 0].set_ylabel('||dL/dW||  (log scale)'); axes[1, 0].set_ylabel('||dL/dW||  (log scale)')
axes[0, 0].legend()
plt.suptitle('Figure 2.3a  Gradient-norm profile through the network', fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
""")

code(r"""
# Figure 2.3b - heatmaps: layer x epoch, for the deepest (12-layer) network in each regime
fig, axes = plt.subplots(1, 3, figsize=(18, 5.2))
for ax, regime in zip(axes, GRAD_REGIMES):
    g = GRAD_RESULTS[(regime, 12)]['grads']
    data = np.log10(g.replace(0, np.nan).T.astype(float))
    sns.heatmap(data, ax=ax, cmap='magma', cbar_kws={'label': 'log10 ||dL/dW||'},
                xticklabels=max(1, len(g) // 10))
    ax.set_title(f'{regime} - 12 hidden layers'); ax.set_xlabel('epoch (0 = init)'); ax.set_ylabel('layer')
plt.suptitle('Figure 2.3b  Gradient magnitude by layer over training', fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
""")

code(r"""
# Figure 2.3c - training dynamics per depth
fig, axes = plt.subplots(2, 3, figsize=(17, 8))
for j, regime in enumerate(GRAD_REGIMES):
    for k, d in enumerate(DEPTHS):
        h = GRAD_RESULTS[(regime, d)]['history']
        axes[0, j].plot(h['loss'], color=PALETTE[k], label=f'{d} layers')
        axes[1, j].plot(h['val_auc'], color=PALETTE[k], label=f'{d} layers')
    axes[0, j].set_title(f'{regime}: training loss'); axes[1, j].set_title(f'{regime}: validation ROC-AUC')
    axes[0, j].set_yscale('log'); axes[1, j].set_ylim(0.4, 1.0); axes[1, j].axhline(.5, ls=':', c='grey')
    axes[1, j].set_xlabel('epoch')
axes[0, 0].legend()
plt.suptitle('Figure 2.3c  Learning progress vs depth', fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
""")

md(r"""
## 2.4 Quantifying vanishing / exploding patterns
Key statistic: **gradient ratio = ‖∂L/∂W₁‖ / ‖∂L/∂W_L‖** (first hidden layer vs last hidden layer) at initialisation.
- ratio ≪ 1 → **vanishing**: early layers learn far more slowly than late layers.
- ratio ≈ 1 → **healthy flow**.
- very large absolute norms (≫ 1), or a run that diverges to NaN → **exploding**.

The **log₁₀ decay per layer** is the average change in log gradient norm per layer. It indicates how quickly the gradient signal decays (or grows) with depth.
""")

code(r"""
rows = []
for (regime, d), r in GRAD_RESULTS.items():
    g0 = r['grads'].iloc[0].values
    hidden = g0[:-1]                                 # exclude output layer
    ratio = hidden[0] / hidden[-1]
    rows.append({'regime': regime, 'depth': d,
                 'grad_L1_init': hidden[0], 'grad_Llast_init': hidden[-1], 'ratio_first/last': ratio,
                 'log10_change_per_layer': np.log10(ratio) / max(1, d - 1),
                 'max_grad_norm_any_epoch': np.nanmax(r['grads'].values),
                 'diverged': r['diverged'], 'epochs_run': r['epochs_run'],
                 'final_train_loss': r['history']['loss'].iloc[-1], 'val_roc_auc': r['val']['roc_auc']})
GRAD_SUMMARY = pd.DataFrame(rows)
display(GRAD_SUMMARY.style.format({c: '{:.3e}' for c in ['grad_L1_init', 'grad_Llast_init', 'ratio_first/last',
                                                       'max_grad_norm_any_epoch']} |
                                  {'log10_change_per_layer': '{:.3f}', 'final_train_loss': '{:.4f}', 'val_roc_auc': '{:.4f}'}))

fig, ax = plt.subplots(1, 3, figsize=(17, 4.3))
for k, regime in enumerate(GRAD_REGIMES):
    s = GRAD_SUMMARY[GRAD_SUMMARY.regime == regime]
    ax[0].semilogy(s.depth, s['ratio_first/last'], '-o', color=PALETTE[k], label=regime)
    ax[1].semilogy(s.depth, s['max_grad_norm_any_epoch'], '-o', color=PALETTE[k], label=regime)
    ax[2].plot(s.depth, s['val_roc_auc'], '-o', color=PALETTE[k], label=regime)
ax[0].axhline(1, ls=':', c='grey'); ax[0].set(title='Gradient ratio (layer 1 / last hidden) at init', xlabel='hidden layers')
ax[1].set(title='Max gradient norm observed', xlabel='hidden layers')
ax[2].axhline(.5, ls=':', c='grey'); ax[2].set(title='Validation ROC-AUC', xlabel='hidden layers', ylim=(0.4, 1))
ax[0].legend(fontsize=9); plt.tight_layout(); plt.show()
""")

md(r"""
## 2.5 Remedies for exploding gradients (12-layer network, regime C)
Two fixes are tested: **gradient clipping** (`clipnorm=1.0`, which rescales any update whose global norm exceeds 1) and **batch normalisation** (which re-standardises pre-activations at every layer, so the bad initial scale cannot compound).
""")

code(r"""
fix_cfgs = {
    'C. baseline (no fix)': dict(),
    'C + gradient clipping (clipnorm=1)': dict(opt_fn=lambda: keras.optimizers.SGD(0.01, momentum=0.9, clipnorm=1.0)),
    'C + BatchNorm': dict(extra_kw=dict(norm='batch')),
    'A. sigmoid + BatchNorm (vanishing fix)': dict(regime='A. Sigmoid + Xavier', extra_kw=dict(norm='batch')),
}
FIX_RESULTS = {}
for name, kw in fix_cfgs.items():
    kw = dict(kw); regime = kw.pop('regime', 'C. ReLU + N(0,0.5)')
    FIX_RESULTS[name] = run_gradient_experiment(GRAD_REGIMES[regime], 12, **kw)

fig, ax = plt.subplots(1, 2, figsize=(15, 4.5))
for k, (name, r) in enumerate(FIX_RESULTS.items()):
    g = r['grads']; ax[0].semilogy(np.arange(1, g.shape[1] + 1), g.iloc[0].values, '-o', ms=4, color=PALETTE[k], label=name)
    ax[1].plot(r['history']['val_auc'], color=PALETTE[k], label=name)
ax[0].set(title='Gradient profile at initialisation (12 layers)', xlabel='layer', ylabel='||dL/dW||')
ax[1].set(title='Validation ROC-AUC', xlabel='epoch', ylim=(0.4, 1)); ax[1].legend(fontsize=9)
plt.tight_layout(); plt.show()
pd.DataFrame({n: {'diverged': r['diverged'], 'epochs_run': r['epochs_run'], 'val_roc_auc': r['val']['roc_auc'],
                  'max_grad_norm': np.nanmax(r['grads'].values)} for n, r in FIX_RESULTS.items()}).T
""")

md(r"""
<!--INTERP_PART2-->
""")

# ----------------------------------------------------------------------------
# PART 3
# ----------------------------------------------------------------------------
md(r"""
---
# Part 3: Advanced Optimization Techniques (15 points)

All comparisons use the shared `run_config` harness: the same data, class weights, batch size (64) and seeds (3 seeds, mean ± std). Unless a comparison needs otherwise, `EarlyStopping(val_loss, patience=20, restore_best_weights=True)` is applied, so each configuration is judged at its best epoch rather than at an arbitrary cut-off.
""")

code(r"""
def run_config(name, model_kw=None, opt_fn=lambda: keras.optimizers.Adam(1e-3), seeds=SEEDS, epochs=None,
               early_stop=True, patience=20, es_monitor='val_loss', restore=True, extra_callbacks=None,
               monitor_grads=False, batch_size=64, X_tr=None, y_tr=None):
    epochs = epochs or E(150)
    X_tr = X_train if X_tr is None else X_tr
    y_tr = y_train if y_tr is None else y_tr
    runs = []
    for s in seeds:
        keras.utils.set_random_seed(s)
        model = build_mlp(**(model_kw or {}))
        model.compile(optimizer=opt_fn(), loss='binary_crossentropy', metrics=METRICS())
        cbs = [keras.callbacks.TerminateOnNaN()]
        if early_stop:
            cbs.append(keras.callbacks.EarlyStopping(monitor=es_monitor, mode='max' if 'auc' in es_monitor else 'min',
                                                     patience=patience, restore_best_weights=restore))
        lr_log = LRLogger(); cbs.append(lr_log)
        gm = GradientMonitor(X_tr, y_tr) if (monitor_grads and s == seeds[0]) else None
        if gm: cbs.append(gm)
        if extra_callbacks: cbs += extra_callbacks()
        t = time.time()
        h = model.fit(X_tr, y_tr, validation_data=(X_val, y_val), epochs=epochs, batch_size=batch_size,
                      class_weight=CLASS_WEIGHT, verbose=0, callbacks=cbs)
        hist = pd.DataFrame(h.history); hist['lr_logged'] = lr_log.lrs[:len(hist)]
        vm, tm = evaluate(model, X_val, y_val), evaluate(model, X_tr, y_tr)
        runs.append(dict(seed=s, model=model, history=hist, grads=gm.frame() if gm else None, time=time.time() - t,
                         epochs_run=len(hist), best_epoch=int(np.nanargmin(hist['val_loss'].values)) + 1
                         if np.isfinite(hist['val_loss']).any() else np.nan,
                         **{f'val_{k}': v for k, v in vm.items()}, **{f'train_{k}': v for k, v in tm.items()}))
    return dict(name=name, runs=runs)

def summarise(results, cols=('val_roc_auc', 'val_pr_auc', 'val_f1', 'val_mcc', 'val_log_loss', 'train_roc_auc',
                             'best_epoch', 'epochs_run', 'time')):
    out = {}
    for r in results:
        df_r = pd.DataFrame([{c: run[c] for c in cols} for run in r['runs']])
        out[r['name']] = {**{f'{c}_mean': df_r[c].mean() for c in cols}, 'val_roc_auc_std': df_r['val_roc_auc'].std()}
    t = pd.DataFrame(out).T
    t['auc_gap(train-val)'] = t['train_roc_auc_mean'] - t['val_roc_auc_mean']
    order = ['val_roc_auc_mean', 'val_roc_auc_std', 'val_pr_auc_mean', 'val_f1_mean', 'val_mcc_mean', 'val_log_loss_mean',
             'train_roc_auc_mean', 'auc_gap(train-val)', 'best_epoch_mean', 'epochs_run_mean', 'time_mean']
    return t[order].sort_values('val_roc_auc_mean', ascending=False)

def plot_curves(results, metric='val_loss', title='', ax=None, logy=False):
    ax = ax or plt.gca()
    for k, r in enumerate(results):
        for j, run in enumerate(r['runs']):
            ax.plot(run['history'][metric].values, color=PALETTE[k % 10], alpha=1 if j == 0 else .25,
                    label=r['name'] if j == 0 else None)
    ax.set(title=title or metric, xlabel='epoch')
    if logy: ax.set_yscale('log')
    return ax

def bar_auc(summary, ax, title):
    s = summary.sort_values('val_roc_auc_mean')
    ax.barh(s.index, s['val_roc_auc_mean'], xerr=s['val_roc_auc_std'], color=PALETTE[0], alpha=.8, capsize=3)
    lo = max(0.5, np.nanmin(s['val_roc_auc_mean'] - s['val_roc_auc_std'].fillna(0)) - .03)
    ax.set_xlim(lo, 1.0); ax.set_title(title); ax.set_xlabel('validation ROC-AUC (mean ± std over seeds)')
    for i, v in enumerate(s['val_roc_auc_mean']):
        ax.text(v + .003, i, f'{v:.3f}', va='center', fontsize=9)

BASE_MODEL = dict(depth=4, width=64, activation='relu', init='he_normal')
""")

md(r"""
## 3.1 Optimiser comparison: SGD, SGD + Momentum, Adam, RMSprop, AdaGrad
Each optimiser is run first at a standard learning rate. A small learning-rate sweep follows (Section 3.1b), because comparing optimisers at a single learning rate is biased toward whichever one happens to suit that value.
""")

code(r"""
OPTIMIZERS = {
    'SGD (lr=0.01)':                   lambda: keras.optimizers.SGD(0.01),
    'SGD + Nesterov momentum (lr=0.01)': lambda: keras.optimizers.SGD(0.01, momentum=0.9, nesterov=True),
    'Adam (lr=1e-3)':                  lambda: keras.optimizers.Adam(1e-3),
    'RMSprop (lr=1e-3)':               lambda: keras.optimizers.RMSprop(1e-3),
    'AdaGrad (lr=0.05)':               lambda: keras.optimizers.Adagrad(0.05),
}
OPT_RESULTS = [run_config(n, BASE_MODEL, f) for n, f in OPTIMIZERS.items()]
OPT_SUMMARY = summarise(OPT_RESULTS); display(OPT_SUMMARY)

fig, ax = plt.subplots(1, 3, figsize=(18, 4.6))
plot_curves(OPT_RESULTS, 'loss', 'Training loss (class-weighted)', ax[0])
plot_curves(OPT_RESULTS, 'val_loss', 'Validation loss', ax[1]); ax[1].set_ylim(top=0.8); ax[0].legend(fontsize=8)
bar_auc(OPT_SUMMARY, ax[2], 'Optimiser: validation ROC-AUC')
plt.tight_layout(); plt.show()
""")

code(r"""
# 3.1b Learning-rate sensitivity per optimiser (single seed, 3 learning rates)
LR_GRID = [1e-3, 1e-2, 1e-1]
opt_factory = {'SGD': lambda lr: keras.optimizers.SGD(lr), 'SGD+Momentum': lambda lr: keras.optimizers.SGD(lr, momentum=0.9),
               'Adam': lambda lr: keras.optimizers.Adam(lr), 'RMSprop': lambda lr: keras.optimizers.RMSprop(lr),
               'AdaGrad': lambda lr: keras.optimizers.Adagrad(lr)}
sens = pd.DataFrame(index=list(opt_factory), columns=LR_GRID, dtype=float)
for o, f in opt_factory.items():
    for lr in LR_GRID:
        r = run_config(f'{o}@{lr}', BASE_MODEL, (lambda f=f, lr=lr: f(lr)), seeds=[SEED])
        sens.loc[o, lr] = r['runs'][0]['val_roc_auc']
plt.figure(figsize=(7, 3.8))
sns.heatmap(sens, annot=True, fmt='.3f', cmap='viridis', cbar_kws={'label': 'val ROC-AUC'})
plt.title('Optimiser x learning-rate sensitivity'); plt.xlabel('learning rate'); plt.show()
""")

md(r"""
<!--INTERP_OPT-->

## 3.2 Weight-initialisation strategies
A 6-hidden-layer ReLU network trained with SGD + momentum, where initialisation matters most. Adam would partly compensate for a bad scale. Compared: **Xavier/Glorot** (uniform and normal; Var = 2/(fan_in + fan_out)), **He** (normal and uniform; Var = 2/fan_in, derived for ReLU), **LeCun normal** (Var = 1/fan_in), a too-small N(0, 0.01²), a too-large N(0, 1) and all-**zeros**.

Before training, forward **activation statistics** (std of each layer's output) are also measured. This shows whether the signal is preserved as it travels through the network.
""")

code(r"""
INITS = {
    'Xavier/Glorot uniform': 'glorot_uniform', 'Xavier/Glorot normal': 'glorot_normal',
    'He normal': 'he_normal', 'He uniform': 'he_uniform', 'LeCun normal': 'lecun_normal',
    'Small N(0,0.01)': lambda: keras.initializers.RandomNormal(stddev=0.01),
    'Large N(0,1)': lambda: keras.initializers.RandomNormal(stddev=1.0),
    'Zeros': 'zeros',
}
SGD_M = lambda: keras.optimizers.SGD(0.01, momentum=0.9)

def activation_std_profile(model, X):
    acts = [l.output for l in model.layers if l.name.startswith('act_')]
    probe = keras.Model(model.inputs, acts)
    return [float(np.std(a)) for a in probe.predict(X, verbose=0)]

act_profiles = {}
for n, init in INITS.items():
    keras.utils.set_random_seed(SEED)
    act_profiles[n] = activation_std_profile(build_mlp(depth=6, init=init), X_train)

INIT_RESULTS = [run_config(n, dict(depth=6, width=64, activation='relu', init=i), SGD_M, monitor_grads=True)
                for n, i in INITS.items()]
INIT_SUMMARY = summarise(INIT_RESULTS); display(INIT_SUMMARY)

fig, ax = plt.subplots(1, 3, figsize=(19, 4.8))
for k, (n, prof) in enumerate(act_profiles.items()):
    ax[0].semilogy(range(1, 7), np.maximum(prof, 1e-12), '-o', ms=4, color=PALETTE[k % 10], label=n)
    g = INIT_RESULTS[k]['runs'][0]['grads']
    ax[1].semilogy(range(1, g.shape[1] + 1), np.maximum(g.iloc[0].values, 1e-12), '-o', ms=4, color=PALETTE[k % 10], label=n)
ax[0].set(title='Forward signal: activation std per layer (init)', xlabel='hidden layer')
ax[1].set(title='Backward signal: ||dL/dW|| per layer (init)', xlabel='layer (last = output)')
ax[0].legend(fontsize=8); bar_auc(INIT_SUMMARY, ax[2], 'Initialisation: validation ROC-AUC')
plt.tight_layout(); plt.show()
""")

md(r"""
<!--INTERP_INIT-->

## 3.3 Activation functions: ReLU, Leaky ReLU, ELU, Swish (+ tanh, sigmoid, SELU as references)
Each activation is paired with its matched initialiser (He for the ReLU family and Swish, Glorot for tanh and sigmoid, LeCun for SELU). Training uses a 6-layer network with Adam (lr = 1e-3). After training, the fraction of **dead units** is measured: hidden units whose output is ≤ 0 for every training example, so they pass no gradient (a known ReLU failure mode).
""")

code(r"""
xs = np.linspace(-4, 4, 400)
act_fns = {'ReLU': (np.maximum(0, xs), (xs > 0).astype(float)),
           'Leaky ReLU (0.1)': (np.where(xs > 0, xs, .1 * xs), np.where(xs > 0, 1, .1)),
           'ELU': (np.where(xs > 0, xs, np.exp(xs) - 1), np.where(xs > 0, 1, np.exp(xs))),
           'Swish (x*sigmoid(x))': (xs / (1 + np.exp(-xs)),
                                    (1 / (1 + np.exp(-xs))) * (1 + xs * (1 - 1 / (1 + np.exp(-xs))))),
           'tanh': (np.tanh(xs), 1 - np.tanh(xs) ** 2),
           'sigmoid': (1 / (1 + np.exp(-xs)), (1 / (1 + np.exp(-xs))) * (1 - 1 / (1 + np.exp(-xs))))}
fig, ax = plt.subplots(1, 2, figsize=(14, 4))
for k, (n, (f, df_)) in enumerate(act_fns.items()):
    ax[0].plot(xs, f, label=n, color=PALETTE[k]); ax[1].plot(xs, df_, label=n, color=PALETTE[k])
ax[0].set(title='Activation f(x)', ylim=(-1.5, 4)); ax[1].set(title="Derivative f'(x) - the factor that multiplies the gradient")
ax[1].axhline(.25, ls=':', c='grey'); ax[1].text(-3.9, .27, "sigmoid max = 0.25", fontsize=8); ax[0].legend()
plt.tight_layout(); plt.show()
""")

code(r"""
ACTS = {'ReLU': ('relu', 'he_normal'), 'Leaky ReLU (0.1)': ('leaky_relu', 'he_normal'), 'ELU': ('elu', 'he_normal'),
        'Swish': ('swish', 'he_normal'), 'SELU (+LeCun)': ('selu', 'lecun_normal'),
        'tanh (+Xavier)': ('tanh', 'glorot_uniform'), 'sigmoid (+Xavier)': ('sigmoid', 'glorot_uniform')}
ACT_RESULTS = [run_config(n, dict(depth=6, width=64, activation=a, init=i), monitor_grads=True) for n, (a, i) in ACTS.items()]

def dead_unit_fraction(model, X):
    acts = [l.output for l in model.layers if l.name.startswith('act_')]
    outs = keras.Model(model.inputs, acts).predict(X, verbose=0)
    return float(np.mean(np.concatenate([(o.max(axis=0) <= 1e-8) for o in outs])))

ACT_SUMMARY = summarise(ACT_RESULTS)
ACT_SUMMARY['dead_unit_%'] = [100 * np.mean([dead_unit_fraction(run['model'], X_train) for run in r['runs']])
                              for r in sorted(ACT_RESULTS, key=lambda r: list(ACT_SUMMARY.index).index(r['name']))]
display(ACT_SUMMARY)

fig, ax = plt.subplots(1, 3, figsize=(19, 4.6))
plot_curves(ACT_RESULTS, 'val_loss', 'Validation loss', ax[0]); ax[0].set_ylim(top=0.8); ax[0].legend(fontsize=8)
for k, r in enumerate(ACT_RESULTS):
    g = r['runs'][0]['grads']; ax[1].semilogy(range(1, g.shape[1] + 1), g.iloc[0].values, '-o', ms=4, color=PALETTE[k], label=r['name'])
ax[1].set(title='Gradient profile at init (6 layers)', xlabel='layer')
bar_auc(ACT_SUMMARY, ax[2], 'Activation: validation ROC-AUC'); plt.tight_layout(); plt.show()
""")

md(r"""
<!--INTERP_ACT-->

## 3.4 Batch Normalisation and Layer Normalisation
Two settings:
- **(a) Rescue setting:** a 9-layer **sigmoid** network with SGD + momentum, which vanishes badly in Part 2. Does normalisation restore gradient flow?
- **(b) Modern setting:** a 6-layer ReLU network with Adam. Does normalisation still help once gradients are already healthy?

BatchNorm normalises each unit over the **mini-batch** (and keeps running statistics for inference). LayerNorm normalises over the **features of each sample**, so it behaves the same at train and test time and does not depend on batch size.
""")

code(r"""
NORM_RESULTS_A = [run_config(f'sigmoid-9 | {n}', dict(depth=9, activation='sigmoid', init='glorot_uniform', norm=v),
                             SGD_M, monitor_grads=True) for n, v in [('no norm', None), ('BatchNorm', 'batch'), ('LayerNorm', 'layer')]]
NORM_RESULTS_B = [run_config(f'ReLU-6 | {n}', dict(depth=6, activation='relu', init='he_normal', norm=v), monitor_grads=True)
                  for n, v in [('no norm', None), ('BatchNorm', 'batch'), ('LayerNorm', 'layer')]]
NORM_SUMMARY = summarise(NORM_RESULTS_A + NORM_RESULTS_B); display(NORM_SUMMARY)

fig, ax = plt.subplots(1, 4, figsize=(22, 4.6))
for k, r in enumerate(NORM_RESULTS_A):
    g = r['runs'][0]['grads']; ax[0].semilogy(range(1, g.shape[1] + 1), g.iloc[0].values, '-o', ms=4, color=PALETTE[k], label=r['name'])
    ax[1].plot(r['runs'][0]['history']['val_auc'], color=PALETTE[k], label=r['name'])
for k, r in enumerate(NORM_RESULTS_B):
    ax[2].plot(r['runs'][0]['history']['val_loss'], color=PALETTE[k], label=r['name'])
ax[0].set(title='(a) sigmoid-9: gradient profile at init', xlabel='layer'); ax[0].legend(fontsize=8)
ax[1].set(title='(a) sigmoid-9: validation ROC-AUC', xlabel='epoch', ylim=(.4, 1)); ax[1].legend(fontsize=8)
ax[2].set(title='(b) ReLU-6: validation loss', xlabel='epoch', ylim=(None, .8)); ax[2].legend(fontsize=8)
bar_auc(NORM_SUMMARY, ax[3], 'Normalisation: validation ROC-AUC'); plt.tight_layout(); plt.show()
""")

md(r"""
<!--INTERP_NORM-->

## 3.5 Learning-rate scheduling
The base model uses SGD + momentum with a deliberately aggressive peak learning rate of 0.05, where a schedule matters most. All schedules run for a fixed 100 epochs with no early stopping (early stopping would cut cosine and step schedules short), and are compared on their best and final validation loss, their peak validation AUC during training, and their AUC at the final epoch.

| Schedule | Definition |
|---|---|
| Constant | lr = 0.05 throughout |
| Step decay | lr halves every 20 epochs (`LearningRateScheduler`) |
| Exponential decay | lr = 0.05 · 0.96^(step/steps_per_epoch) (per-step `ExponentialDecay`) |
| Cosine + warm-up | linear warm-up for 5 epochs, then cosine decay to 0 (`CosineDecay` with warm-up) |
| ReduceLROnPlateau | halve the lr when validation loss stalls for 5 epochs (adaptive, feedback-driven) |
""")

code(r"""
LR0, EP_S = 0.05, E(100)
STEPS = math.ceil(len(X_train) / 64)
SCHEDULES = {
    'Constant (0.05)': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9)),
    'Step decay (x0.5 / 20 ep)': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9),
        extra_callbacks=lambda: [keras.callbacks.LearningRateScheduler(lambda ep, lr: LR0 * 0.5 ** (ep // 20))]),
    'Exponential decay': dict(opt_fn=lambda: keras.optimizers.SGD(keras.optimizers.schedules.ExponentialDecay(
        LR0, decay_steps=STEPS, decay_rate=0.96), momentum=0.9)),
    'Cosine + warm-up': dict(opt_fn=lambda: keras.optimizers.SGD(keras.optimizers.schedules.CosineDecay(
        0.0, decay_steps=STEPS * (EP_S - 5), warmup_target=LR0, warmup_steps=STEPS * 5), momentum=0.9)),
    'ReduceLROnPlateau': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9),
        extra_callbacks=lambda: [keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, min_lr=1e-5)]),
}

def run_schedule(name, kw):
    r = run_config(name, BASE_MODEL, epochs=EP_S, early_stop=False, **kw)
    for run in r['runs']:          # evaluate at best epoch by re-training is costly; report curve-based metrics
        h = run['history']; run['best_val_loss'] = h['val_loss'].min(); run['final_val_loss'] = h['val_loss'].iloc[-1]
        run['best_val_auc_epoch'] = h['val_auc'].max()
    return r

SCHED_RESULTS = [run_schedule(n, kw) for n, kw in SCHEDULES.items()]
sched_tbl = pd.DataFrame({r['name']: {
    'best_val_loss': np.mean([x['best_val_loss'] for x in r['runs']]),
    'final_val_loss': np.mean([x['final_val_loss'] for x in r['runs']]),
    'overfit (final - best)': np.mean([x['final_val_loss'] - x['best_val_loss'] for x in r['runs']]),
    'final_val_roc_auc': np.mean([x['val_roc_auc'] for x in r['runs']]),
    'peak_val_auc_curve': np.mean([x['best_val_auc_epoch'] for x in r['runs']]),
    'final_train_auc': np.mean([x['train_roc_auc'] for x in r['runs']])} for r in SCHED_RESULTS}).T
display(sched_tbl.sort_values('best_val_loss'))

fig, ax = plt.subplots(1, 3, figsize=(19, 4.6))
for k, r in enumerate(SCHED_RESULTS):
    h = r['runs'][0]['history']
    ax[0].plot(h['lr_logged'], color=PALETTE[k], label=r['name'])
    ax[1].plot(h['val_loss'], color=PALETTE[k], label=r['name'])
    ax[2].plot(h['loss'], color=PALETTE[k], label=r['name'])
ax[0].set(title='Learning rate per epoch', xlabel='epoch', yscale='log'); ax[0].legend(fontsize=8)
ax[1].set(title='Validation loss', xlabel='epoch', ylim=(None, 1.0)); ax[2].set(title='Training loss', xlabel='epoch', yscale='log')
plt.tight_layout(); plt.show()
""")

md(r"""
<!--INTERP_SCHED-->

## 3.6 Combining the best choices
The best-performing options from Sections 3.1–3.5 are combined into one **tuned** configuration and compared with the default baseline (ReLU + He + Adam, no normalisation) under the same seeds.
""")

code(r"""
# Chosen from the evidence above (see markdown discussion)
TUNED_MODEL = dict(depth=4, width=64, activation='<<TUNED_ACT>>', init='he_normal', norm=<<TUNED_NORM>>)
TUNED_OPT = lambda: keras.optimizers.Adam(keras.optimizers.schedules.CosineDecay(
    0.0, decay_steps=STEPS * (E(120) - 5), warmup_target=3e-3, warmup_steps=STEPS * 5))

COMBO_RESULTS = [run_config('Baseline: ReLU+He+Adam(1e-3)', BASE_MODEL),
                 run_config('Tuned: <<TUNED_LABEL>>', TUNED_MODEL, TUNED_OPT, epochs=E(120), patience=30)]
COMBO_SUMMARY = summarise(COMBO_RESULTS); display(COMBO_SUMMARY)
fig, ax = plt.subplots(1, 2, figsize=(14, 4))
plot_curves(COMBO_RESULTS, 'val_loss', 'Validation loss', ax[0]); ax[0].legend(fontsize=8); ax[0].set_ylim(top=.8)
plot_curves(COMBO_RESULTS, 'val_auc', 'Validation ROC-AUC', ax[1]); ax[1].set_ylim(.7, 1)
plt.tight_layout(); plt.show()
""")

md(r"""
<!--INTERP_COMBO-->
""")

# ----------------------------------------------------------------------------
# PART 4
# ----------------------------------------------------------------------------
md(r"""
---
# Part 4: Regularization & Generalization (6 points)

To make regularisation effects visible, Part 4 uses a deliberately **over-parameterised** network: 4 hidden layers of width 256, about 200k weights for roughly 950 training rows. It is trained with Adam (1e-3) for a fixed 150 epochs and **no early stopping**, so the network has every opportunity to overfit.
""")

code(r"""
OVERFIT_MODEL = dict(depth=4, width=256, activation='relu', init='he_normal')
EP_R = E(150)
SEEDS_R = SEEDS[:2]

def weight_stats(model):
    w = np.concatenate([l.kernel.numpy().ravel() for l in model.layers if isinstance(l, layers.Dense)])
    return dict(l2_norm=float(np.linalg.norm(w)), sparsity_pct=float(100 * np.mean(np.abs(w) < 1e-3)))

def run_reg(name, **kw):
    r = run_config(name, {**OVERFIT_MODEL, **kw.pop('model_kw', {})}, epochs=EP_R, early_stop=False, seeds=SEEDS_R, **kw)
    for run in r['runs']:
        run.update(weight_stats(run['model']))
        run['min_val_loss'] = run['history']['val_loss'].min()
    return r

def reg_table(results):
    t = summarise(results, cols=('val_roc_auc', 'val_pr_auc', 'val_log_loss', 'train_roc_auc', 'train_log_loss',
                                 'best_epoch', 'epochs_run', 'time'))
    extra = pd.DataFrame({r['name']: {k: np.mean([run[k] for run in r['runs']]) for k in ('l2_norm', 'sparsity_pct', 'min_val_loss')}
                          for r in results}).T
    return t.join(extra)
""")

md(r"""
## 4.1 L1, L2 and Elastic-Net weight penalties
- **L1** adds λ·Σ|w|, which pushes weights to exactly zero (sparse, implicit feature selection).
- **L2** (weight decay) adds λ·Σw², which shrinks all weights smoothly.
- **Elastic net** (`L1L2`) combines the two: some sparsity, plus stability when features are correlated.
""")

code(r"""
REG_RESULTS = [run_reg('No regularisation'),
               run_reg('L1 (1e-4)', model_kw=dict(reg=('l1', 1e-4))),
               run_reg('L2 (1e-3)', model_kw=dict(reg=('l2', 1e-3))),
               run_reg('Elastic net (L1 5e-5 + L2 5e-4)', model_kw=dict(reg=('l1l2', 5e-5, 5e-4)))]
REG_SUMMARY = reg_table(REG_RESULTS); display(REG_SUMMARY)

fig, axes = plt.subplots(1, 4, figsize=(22, 4.3), sharey=True)
for ax, r in zip(axes, REG_RESULTS):
    h = r['runs'][0]['history']; ax.plot(h['loss'], label='train (weighted)'); ax.plot(h['val_loss'], label='validation')
    ax.set(title=r['name'], xlabel='epoch', ylim=(0, 1.5))
axes[0].legend(); axes[0].set_ylabel('loss'); plt.suptitle('Learning curves under weight penalties', weight='bold')
plt.tight_layout(); plt.show()

fig, ax = plt.subplots(figsize=(10, 3.8))
for k, r in enumerate(REG_RESULTS):
    w = np.concatenate([l.kernel.numpy().ravel() for l in r['runs'][0]['model'].layers if isinstance(l, layers.Dense)])
    ax.hist(w, bins=200, range=(-.4, .4), histtype='step', lw=1.6, color=PALETTE[k], label=r['name'], density=True)
ax.set(title='Weight distributions (L1 -> spike at 0, L2 -> narrower)', yscale='log'); ax.legend(fontsize=8)
plt.tight_layout(); plt.show()
""")

md(r"""
### 4.1b Validation curve — L2 strength
A validation curve sweeps a single complexity knob. Small λ gives **high variance** (a large train–validation gap); large λ gives **high bias** (both scores fall).
""")

code(r"""
L2_GRID = [0, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1]
VC_RESULTS = [run_reg(f'L2={lam:g}', model_kw=dict(reg=('l2', lam) if lam else None)) for lam in L2_GRID]
vc = reg_table(VC_RESULTS).loc[[r['name'] for r in VC_RESULTS]]
xs_ = [1e-6] + L2_GRID[1:]
fig, ax = plt.subplots(1, 2, figsize=(14, 4.2))
ax[0].semilogx(xs_, vc['train_roc_auc_mean'], '-o', label='train'); ax[0].semilogx(xs_, vc['val_roc_auc_mean'], '-o', label='validation')
ax[0].set(title='Validation curve: ROC-AUC vs L2 lambda', xlabel='lambda (0 plotted at 1e-6)', ylabel='ROC-AUC'); ax[0].legend()
ax[1].semilogx(xs_, vc['train_log_loss_mean'], '-o', label='train'); ax[1].semilogx(xs_, vc['val_log_loss_mean'], '-o', label='validation')
ax[1].set(title='Validation curve: log-loss vs L2 lambda', xlabel='lambda', ylabel='log-loss'); ax[1].legend()
plt.tight_layout(); plt.show()
vc[['train_roc_auc_mean', 'val_roc_auc_mean', 'auc_gap(train-val)', 'train_log_loss_mean', 'val_log_loss_mean', 'l2_norm']]
""")

md(r"""
## 4.2 Dropout — rates and positions
**Rates:** 0, 0.1, 0.2, 0.3 and 0.5 after every hidden layer. **Positions** (at rate 0.3): only on the inputs (0.1, a form of feature noise), only the **early** half of the hidden layers, only the **late** half, and inputs plus all hidden layers.
""")

code(r"""
DROP_RATE_RESULTS = [run_reg(f'dropout {p} (all hidden)', model_kw=dict(dropout=p)) for p in [0.0, 0.1, 0.2, 0.3, 0.5]]
DROP_POS_RESULTS = [run_reg('input only (0.1)', model_kw=dict(input_dropout=0.1)),
                    run_reg('early layers (0.3)', model_kw=dict(dropout=0.3, dropout_positions='early')),
                    run_reg('late layers (0.3)', model_kw=dict(dropout=0.3, dropout_positions='late')),
                    run_reg('all hidden (0.3)', model_kw=dict(dropout=0.3)),
                    run_reg('input 0.1 + all hidden 0.3', model_kw=dict(dropout=0.3, input_dropout=0.1))]
DROP_SUMMARY = reg_table(DROP_RATE_RESULTS + DROP_POS_RESULTS); display(DROP_SUMMARY)

fig, ax = plt.subplots(1, 3, figsize=(19, 4.3))
rates = [0.0, 0.1, 0.2, 0.3, 0.5]; dr = reg_table(DROP_RATE_RESULTS).loc[[r['name'] for r in DROP_RATE_RESULTS]]
ax[0].plot(rates, dr['train_roc_auc_mean'], '-o', label='train'); ax[0].plot(rates, dr['val_roc_auc_mean'], '-o', label='validation')
ax[0].set(title='ROC-AUC vs dropout rate', xlabel='dropout rate'); ax[0].legend()
ax[1].plot(rates, dr['min_val_loss'], '-o', label='best val loss'); ax[1].plot(rates, dr['val_log_loss_mean'], '-o', label='final val loss')
ax[1].set(title='Validation loss vs dropout rate', xlabel='dropout rate'); ax[1].legend()
dp = reg_table(DROP_POS_RESULTS)
ax[2].barh(dp.index, dp['auc_gap(train-val)'], color=PALETTE[1]); ax[2].set(title='Generalisation gap (train - val AUC) by position')
plt.tight_layout(); plt.show()
""")

md(r"""
## 4.3 Early-stopping strategies
Early stopping is applied to the same over-parameterised network with a 300-epoch budget. Compared: no stopping, `val_loss` with patience 5, patience 20, patience 20 **without** restoring the best weights, monitoring `val_auc` instead of loss, and a `min_delta` threshold.
""")

code(r"""
ES = {'No early stopping (300 ep)': dict(early_stop=False),
      'val_loss, patience=5, restore': dict(patience=5),
      'val_loss, patience=20, restore': dict(patience=20),
      'val_loss, patience=20, NO restore': dict(patience=20, restore=False),
      'val_auc (max), patience=20, restore': dict(patience=20, es_monitor='val_auc'),
      'val_loss, min_delta=1e-3, patience=10': dict(patience=10,
            extra_callbacks=None)}
ES_RESULTS = []
for n, kw in ES.items():
    kw = dict(kw)
    if 'min_delta' in n:   # custom callback with min_delta (run_config's default ES replaced)
        kw = dict(early_stop=False, extra_callbacks=lambda: [keras.callbacks.EarlyStopping(
            monitor='val_loss', min_delta=1e-3, patience=10, restore_best_weights=True)])
    ES_RESULTS.append(run_config(n, OVERFIT_MODEL, epochs=E(300), seeds=SEEDS_R, **kw))
ES_SUMMARY = summarise(ES_RESULTS); display(ES_SUMMARY[['val_roc_auc_mean', 'val_pr_auc_mean', 'val_log_loss_mean',
                                                        'train_roc_auc_mean', 'auc_gap(train-val)', 'best_epoch_mean',
                                                        'epochs_run_mean', 'time_mean']])
fig, ax = plt.subplots(figsize=(12, 4.3))
full = ES_RESULTS[0]['runs'][0]['history']['val_loss']; ax.plot(full.values, color='grey', alpha=.6, label='val loss (no stopping)')
for k, r in enumerate(ES_RESULTS[1:], 1):
    e = r['runs'][0]['epochs_run']; ax.axvline(e, color=PALETTE[k], ls='--', label=f"{r['name']} -> stops @ {e}")
ax.axvline(int(full.idxmin()) + 1, color='k', lw=2, label=f'true min val loss @ {int(full.idxmin()) + 1}')
ax.set(title='Where each strategy stops (seed 42)', xlabel='epoch', ylabel='validation loss', ylim=(0, min(3, full.max())))
ax.legend(fontsize=8); plt.tight_layout(); plt.show()
""")

md(r"""
## 4.4 Bias–variance trade-off: model capacity sweep
Capacity is varied through width (2 hidden layers, 2 to 512 units), with no regularisation and a fixed epoch budget. Training error keeps falling as capacity grows (bias shrinks). Validation error falls and then rises once variance dominates.
""")

code(r"""
WIDTHS = [2, 4, 8, 32, 128, 512]
CAP_RESULTS = [run_config(f'width={w}', dict(depth=2, width=w), epochs=E(150), early_stop=False, seeds=SEEDS_R) for w in WIDTHS]
cap = summarise(CAP_RESULTS, cols=('val_roc_auc', 'train_roc_auc', 'val_log_loss', 'train_log_loss', 'best_epoch', 'epochs_run', 'time'))
cap = cap.loc[[r['name'] for r in CAP_RESULTS]]
params = [build_mlp(depth=2, width=w).count_params() for w in WIDTHS]
fig, ax = plt.subplots(1, 2, figsize=(14, 4.2))
ax[0].semilogx(params, 1 - cap['train_roc_auc_mean'], '-o', label='train error (1-AUC)')
ax[0].semilogx(params, 1 - cap['val_roc_auc_mean'], '-o', label='validation error (1-AUC)')
ax[0].set(title='Bias-variance: error vs capacity', xlabel='# parameters'); ax[0].legend()
ax[1].semilogx(params, cap['train_log_loss_mean'], '-o', label='train log-loss')
ax[1].semilogx(params, cap['val_log_loss_mean'], '-o', label='validation log-loss')
ax[1].set(title='Log-loss vs capacity', xlabel='# parameters'); ax[1].legend()
plt.tight_layout(); plt.show()
cap.assign(params=params)[['params', 'train_roc_auc_mean', 'val_roc_auc_mean', 'auc_gap(train-val)', 'train_log_loss_mean', 'val_log_loss_mean']]
""")

md(r"""
## 4.5 Learning curves vs training-set size
Three models are trained on 10–100% of the training set (stratified subsamples) and always evaluated on the full validation set:
- **High-bias:** 1 hidden layer of 2 units with strong L2. Expect train and validation scores to converge, both low.
- **High-variance:** the over-parameterised 4×256 network with no regularisation. Expect a large gap that narrows only slowly with more data.
- **Regularised:** the tuned configuration plus L2, dropout and early stopping. Expect a small gap and the best validation score.
""")

code(r"""
FRACS = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0]
LC_MODELS = {
    'High-bias (1x2, L2=1e-1)': dict(model_kw=dict(depth=1, width=2, reg=('l2', 1e-1)), early_stop=False, epochs=E(150)),
    'High-variance (4x256, no reg)': dict(model_kw=OVERFIT_MODEL, early_stop=False, epochs=E(150)),
    'Regularised (tuned + L2 + dropout + ES)': dict(model_kw=dict(TUNED_MODEL, width=128, dropout=0.3, reg=('l2', 1e-3)),
                                                    opt_fn=TUNED_OPT, epochs=E(120), patience=30),
}
lc_rows = []
for name, kw in LC_MODELS.items():
    for f in FRACS:
        if f < 1.0:
            sub, _ = train_test_split(np.arange(len(X_train)), train_size=f, stratify=y_train, random_state=SEED)
        else:
            sub = np.arange(len(X_train))
        r = run_config(f'{name}@{f}', seeds=SEEDS_R, X_tr=X_train[sub], y_tr=y_train[sub], **kw)
        for run in r['runs']:
            lc_rows.append(dict(model=name, frac=f, n=len(sub), train_auc=run['train_roc_auc'], val_auc=run['val_roc_auc'],
                                train_loss=run['train_log_loss'], val_loss=run['val_log_loss']))
LC = pd.DataFrame(lc_rows)
fig, axes = plt.subplots(1, 3, figsize=(19, 4.3), sharey=True)
for ax, (name, g) in zip(axes, LC.groupby('model', sort=False)):
    s = g.groupby('n')[['train_auc', 'val_auc']].agg(['mean', 'std'])
    for col, c in [('train_auc', PALETTE[0]), ('val_auc', PALETTE[3])]:
        ax.plot(s.index, s[(col, 'mean')], '-o', color=c, label=col.replace('_auc', ''))
        ax.fill_between(s.index, s[(col, 'mean')] - s[(col, 'std')].fillna(0), s[(col, 'mean')] + s[(col, 'std')].fillna(0), color=c, alpha=.15)
    ax.set(title=name, xlabel='# training samples', ylim=(.5, 1.01))
axes[0].set_ylabel('ROC-AUC'); axes[0].legend(); plt.suptitle('Learning curves vs training-set size', weight='bold')
plt.tight_layout(); plt.show()
LC.groupby(['model', 'n'], sort=False)[['train_auc', 'val_auc']].mean().unstack(0).round(3)
""")

md(r"""
<!--INTERP_PART4-->

## 4.6 Final model — held-out test evaluation
The final configuration combines the Part 3 choices with the Part 4 regularisers (L2, dropout and early stopping). It is trained on the training split, with the validation split used **only** for early stopping and for choosing the decision threshold (the one that maximises F1 on validation). It is then scored **once** on the untouched test split, alongside the classical baselines. A **stratified 5-fold cross-validation** on train + validation checks how stable the configuration is across different data partitions; the preprocessing is re-fit inside every fold to avoid leakage.
""")

code(r"""
FINAL_MODEL = dict(TUNED_MODEL, width=128, dropout=0.3, reg=('l2', 1e-3))
final_runs = run_config('FINAL', FINAL_MODEL, TUNED_OPT, epochs=E(120), patience=30)['runs']
final = max(final_runs, key=lambda r: r['val_roc_auc'])['model']     # pick seed on VALIDATION only

p_val = final.predict(X_val, verbose=0).ravel()
prec, rec, thr = precision_recall_curve(y_val, p_val)
f1s = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-9, None)
BEST_THR = float(thr[np.nanargmax(f1s)])
print(f'Decision threshold chosen on validation (max F1): {BEST_THR:.3f}')

def test_metrics(p, y, thr):
    yhat = (p >= thr).astype(int)
    return {'ROC-AUC': roc_auc_score(y, p), 'PR-AUC': average_precision_score(y, p), 'F1': f1_score(y, yhat),
            'Precision': precision_score(y, yhat, zero_division=0), 'Recall': recall_score(y, yhat),
            'Balanced acc.': balanced_accuracy_score(y, yhat), 'MCC': matthews_corrcoef(y, yhat),
            'Brier': brier_score_loss(y, p), 'Log-loss': log_loss(y, np.clip(p, 1e-7, 1 - 1e-7))}

p_test = final.predict(X_test, verbose=0).ravel()
rows = {'Neural net (final, thr=val-opt)': test_metrics(p_test, y_test, BEST_THR),
        'Neural net (final, thr=0.5)': test_metrics(p_test, y_test, 0.5)}
for name, mdl in [('Logistic regression', LogisticRegression(max_iter=2000, class_weight='balanced')),
                  ('Random forest', RandomForestClassifier(n_estimators=500, min_samples_leaf=2, class_weight='balanced_subsample',
                                                           random_state=SEED, n_jobs=-1))]:
    mdl.fit(X_train, y_train); pv = mdl.predict_proba(X_val)[:, 1]
    pr_, rc_, th_ = precision_recall_curve(y_val, pv); f_ = 2 * pr_[:-1] * rc_[:-1] / np.clip(pr_[:-1] + rc_[:-1], 1e-9, None)
    rows[name] = test_metrics(mdl.predict_proba(X_test)[:, 1], y_test, float(th_[np.nanargmax(f_)]))
TEST_TABLE = pd.DataFrame(rows).T
TEST_TABLE
""")

code(r"""
fig, ax = plt.subplots(1, 4, figsize=(22, 4.6))
cm = confusion_matrix(y_test, (p_test >= BEST_THR).astype(int))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False, ax=ax[0],
            xticklabels=['pred not good', 'pred good'], yticklabels=['not good', 'good'])
ax[0].set_title(f'Confusion matrix (test, thr={BEST_THR:.2f})')
fpr, tpr, _ = roc_curve(y_test, p_test); ax[1].plot(fpr, tpr, label=f'AUC={roc_auc_score(y_test, p_test):.3f}')
ax[1].plot([0, 1], [0, 1], ':', c='grey'); ax[1].set(title='ROC curve (test)', xlabel='FPR', ylabel='TPR'); ax[1].legend()
pr, rc, _ = precision_recall_curve(y_test, p_test); ax[2].plot(rc, pr, label=f'AP={average_precision_score(y_test, p_test):.3f}')
ax[2].axhline(y_test.mean(), ls=':', c='grey', label='no-skill'); ax[2].set(title='Precision-recall (test)', xlabel='recall', ylabel='precision'); ax[2].legend()
fp, mp = calibration_curve(y_test, p_test, n_bins=8, strategy='quantile')
ax[3].plot(mp, fp, '-o', label='model'); ax[3].plot([0, 1], [0, 1], ':', c='grey', label='perfect')
ax[3].set(title='Calibration (test)', xlabel='mean predicted prob.', ylabel='observed frequency'); ax[3].legend()
plt.tight_layout(); plt.show()
print(classification_report(y_test, (p_test >= BEST_THR).astype(int), target_names=['not good', 'good'], digits=3))
""")

code(r"""
# Stratified 5-fold CV on train+validation; preprocessing re-fit inside every fold
df_trva = pd.concat([df_tr, df_va]); y_trva = df_trva['good'].values
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
cv_rows = []
for fold, (a, b) in enumerate(skf.split(df_trva, y_trva), 1):
    pre_f = make_preprocessor(NUMERIC, CATEGORICAL).fit(df_trva.iloc[a])
    Xa = pd.DataFrame(pre_f.transform(df_trva.iloc[a]), columns=feat_names_full)[SELECTED].values.astype('float32')
    Xb = pd.DataFrame(pre_f.transform(df_trva.iloc[b]), columns=feat_names_full)[SELECTED].values.astype('float32')
    keras.utils.set_random_seed(SEED + fold)
    mdl = build_mlp(**FINAL_MODEL); mdl.compile(optimizer=TUNED_OPT(), loss='binary_crossentropy', metrics=METRICS())
    cwf = compute_class_weight('balanced', classes=np.array([0, 1]), y=y_trva[a])
    # inner hold-out (15% of the fold's training part) for early stopping
    ia, ib = train_test_split(np.arange(len(a)), test_size=0.15, stratify=y_trva[a], random_state=SEED)
    mdl.fit(Xa[ia], y_trva[a][ia], validation_data=(Xa[ib], y_trva[a][ib]), epochs=E(120), batch_size=64, verbose=0,
            class_weight={0: cwf[0], 1: cwf[1]},
            callbacks=[keras.callbacks.EarlyStopping('val_loss', patience=30, restore_best_weights=True)])
    pb = mdl.predict(Xb, verbose=0).ravel()
    cv_rows.append({'fold': fold, 'roc_auc': roc_auc_score(y_trva[b], pb), 'pr_auc': average_precision_score(y_trva[b], pb)})
CV = pd.DataFrame(cv_rows).set_index('fold')
display(CV.T)
print(f"5-fold CV ROC-AUC = {CV.roc_auc.mean():.3f} ± {CV.roc_auc.std():.3f} | PR-AUC = {CV.pr_auc.mean():.3f} ± {CV.pr_auc.std():.3f}")
""")

md(r"""
## 4.7 Subgroup check (supports the fairness discussion in Part 5)
The test performance is broken down by `alcohol_band`. If the model relies heavily on alcohol, low-alcohol wines that tasters do rate highly could be systematically missed. The subgroups are small, so these figures are indicative only.
""")

code(r"""
te = df_te.assign(p=p_test, pred=(p_test >= BEST_THR).astype(int))
sg = te.groupby('alcohol_band').apply(lambda g: pd.Series({
    'n': len(g), 'actual_good_rate': g['good'].mean(), 'predicted_good_rate': g['pred'].mean(),
    'recall(TPR)': recall_score(g['good'], g['pred'], zero_division=0) if g['good'].sum() else np.nan,
    'false_positive_rate': ((g['pred'] == 1) & (g['good'] == 0)).sum() / max(1, (g['good'] == 0).sum()),
    'mean_score': g['p'].mean()})).reindex(['low', 'medium', 'high'])
sg
""")

md(r"""
---
# Part 5: Written Analysis & Reflection (4 points)

<!--INTERP_PART5-->
""")

md(r"""
---
## References
- Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). Modeling wine preferences by data mining from physicochemical properties. *Decision Support Systems, 47*(4), 547–553.
- Glorot, X., & Bengio, Y. (2010). Understanding the difficulty of training deep feedforward neural networks. *AISTATS*.
- He, K., Zhang, X., Ren, S., & Sun, J. (2015). Delving deep into rectifiers. *ICCV*.
- Ioffe, S., & Szegedy, C. (2015). Batch normalization. *ICML*.
- Ba, J. L., Kiros, J. R., & Hinton, G. E. (2016). Layer normalization. *arXiv:1607.06450*.
- Kingma, D. P., & Ba, J. (2015). Adam: A method for stochastic optimization. *ICLR*.
- Duchi, J., Hazan, E., & Singer, Y. (2011). Adaptive subgradient methods (AdaGrad). *JMLR*.
- Srivastava, N., et al. (2014). Dropout. *JMLR, 15*, 1929–1958.
- Ramachandran, P., Zoph, B., & Le, Q. V. (2017). Searching for activation functions (Swish). *arXiv:1710.05941*.
- Loshchilov, I., & Hutter, F. (2017). SGDR: Stochastic gradient descent with warm restarts. *ICLR*.
- Pascanu, R., Mikolov, T., & Bengio, Y. (2013). On the difficulty of training recurrent neural networks (gradient clipping). *ICML*.
""")

nb = nbf.v4.new_notebook()
nb['cells'] = cells
nb['metadata'] = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                  'language_info': {'name': 'python'}, 'colab': {'provenance': []}}

if __name__ == '__main__':
    import sys
    tuned = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {'act': 'swish', 'norm': 'None', 'label': 'Swish+He+Adam(cosine, warm-up)'}
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            c['source'] = (c['source'].replace('<<TUNED_ACT>>', tuned['act']).replace('<<TUNED_NORM>>', tuned['norm'])
                           .replace('<<TUNED_LABEL>>', tuned['label']))
    out = HERE / 'Week2_Case_Study_Tamara_Dinneen.ipynb'
    nbf.write(nb, out)
    print('wrote', out, len(nb['cells']), 'cells')
