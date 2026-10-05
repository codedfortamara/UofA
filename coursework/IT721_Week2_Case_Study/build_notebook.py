"""Builds Week2_Case_Study_Tamara_Dinneen.ipynb from the course template.

The template's headings and cells are kept in their original order: its code cells
are filled in, and extra cells are added *under* each Part, as the template instructs.

Run:  python build_notebook.py ['{"act": "elu", "norm": "None", "label": "..."}']
"""
import copy
import json
import sys
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).parent
WIDE = ('swish', 'Swish')          # activation of the 'wide + regularised' CV finalist
TEMPLATE = HERE / 'Case_Study_2_Assignment_Template_File.ipynb'
OUT = HERE / 'Week2_Case_Study_Tamara_Dinneen.ipynb'


def md(text):
    return nbf.v4.new_markdown_cell(text.strip('\n'))


def code(text):
    return nbf.v4.new_code_cell(text.strip('\n'))


# =============================================================================
# Header (inserted after the template's "How to use" cell)
# =============================================================================
HEADER = [md(r"""
**Student:** Tamara Dinneen &nbsp;|&nbsp; **Course:** IT721 Applied Research Topics in Deep Learning &nbsp;|&nbsp; **Week 2 Case Study**

**Dataset:** Red Wine Quality (Cortez et al., 2009), Kaggle `uciml/red-wine-quality-cortez-et-al-2009`: 1,599 wines, 11 physicochemical inputs and a sensory `quality` score.

**Task framing.** Following the template's model builder (a single linear output unit, `loss='mse'`), the networks **regress the quality score**. The split is **stratified on the score**. Models are evaluated with regression metrics (RMSE, MAE, R²) and also with metrics suited to an ordinal score: **quadratic-weighted kappa (QWK)** on the rounded predictions, exact and within-±1 accuracy, and the ROC-AUC of the predicted score for flagging "good" wines (quality ≥ 7).

**Experimental protocol** (from the course guide: *run a baseline, change one parameter, re-run and compare*)
- Each experiment changes **one factor** relative to a stated baseline. Everything else stays fixed: data, batch size 64, seeds, and early-stopping rule.
- Comparisons are repeated over **2 random seeds** and reported as mean ± std.
- All model selection uses the **validation** split. The **test** split is used **once**, in the final evaluation (Part 4.6).
- Figures are numbered and every discussion follows **Observation → Technical reason → Practical impact**.

Runtime: about 15–20 minutes for *Run all* on Colab. Set `FAST = True` in Part 0 for a roughly 5-minute smoke run.
""")]

# =============================================================================
# Part 0 - fill template setup cell
# =============================================================================
SETUP = r"""
# ---- Part 0: Environment Setup ----
# Install/Import libraries
# !pip install -q numpy pandas matplotlib seaborn scikit-learn tensorflow

import numpy as np, pandas as pd, matplotlib.pyplot as plt, seaborn as sns, random
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

SEED = 42
np.random.seed(SEED)
random.seed(SEED)
tf.random.set_seed(SEED)

# ---- additional imports & settings used in this solution ----
import os, time, math, warnings
warnings.filterwarnings('ignore')
from scipy import stats
from tensorflow.keras import regularizers
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import PowerTransformer, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.feature_selection import mutual_info_regression
from sklearn.linear_model import Lasso, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (mean_squared_error, mean_absolute_error, r2_score, cohen_kappa_score,
                             roc_auc_score, confusion_matrix, roc_curve)

FAST = False                              # True = quick smoke run (1 seed, ~1/3 of the epochs)
SEEDS = [42] if FAST else [42, 7]
def E(n):                                 # epoch budget helper
    return max(5, int(n * (0.35 if FAST else 1.0)))

keras.utils.set_random_seed(SEED)         # seeds python, numpy and TF in one call
tf.get_logger().setLevel('ERROR')          # silence tf.function retracing notices (one model is built per experiment)
pd.set_option('display.float_format', lambda v: f'{v:,.4f}')
pd.set_option('display.max_columns', 40)
sns.set_theme(style='whitegrid', context='notebook')
plt.rcParams.update({'figure.dpi': 80, 'axes.titleweight': 'bold'})
PAL = sns.color_palette('tab10')
T_START = time.time()
print('TensorFlow', tf.__version__, '| GPU:', tf.config.list_physical_devices('GPU'))
"""

# =============================================================================
# Part 1
# =============================================================================
P1_FILL = r"""
# Load dataset (local copy / Google Drive first, public mirror of the same Kaggle-UCI file as fallback)
DATA_URL = 'https://raw.githubusercontent.com/plotly/datasets/master/winequality-red.csv'
CANDIDATES = ['winequality-red.csv', '/content/winequality-red.csv',
              '/content/drive/MyDrive/DBA/IT 721 DL/Assignment2/winequality-red.csv']
try:
    from google.colab import drive
    drive.mount('/content/drive')
except Exception:
    pass
path = next((p for p in CANDIDATES if os.path.exists(p)), None)
df_raw = pd.read_csv(path or DATA_URL, encoding='utf-8-sig')
if df_raw.shape[1] == 1:                      # UCI original is ';'-separated
    df_raw = pd.read_csv(path or DATA_URL, sep=';', encoding='utf-8-sig')
df_raw.columns = [c.strip() for c in df_raw.columns]
FEATURES = [c for c in df_raw.columns if c != 'quality']
print('Source:', path or DATA_URL, '| shape:', df_raw.shape)
print('Missing values:', int(df_raw.isna().sum().sum()), '| exact duplicate rows:', int(df_raw.duplicated().sum()))
display(df_raw.head())

# EDA, distributions, correlations -> sections 1.1-1.2 below
# Feature engineering             -> section 1.3
# Scaling / encoding / selection  -> sections 1.5-1.6
# Stratified splits               -> section 1.4
"""

P1 = [
md(r"""
## 1.1 Dataset overview and target distribution
"""),
code(r"""
fig, ax = plt.subplots(1, 2, figsize=(13, 3.8))
q = df_raw['quality'].value_counts().sort_index()
ax[0].bar(q.index, q.values, color=PAL[0])
for i, v in zip(q.index, q.values): ax[0].text(i, v + 10, str(v), ha='center')
ax[0].set(title='Figure 1.1a  Quality score distribution', xlabel='quality', ylabel='count')
dup_q = df_raw[df_raw.duplicated(keep=False)]['quality'].value_counts().sort_index()
ax[1].bar(dup_q.index, dup_q.values, color=PAL[1])
ax[1].set(title='Figure 1.1b  Rows involved in exact duplicates, by score', xlabel='quality')
plt.tight_layout(); plt.show()
print(df_raw.dtypes.value_counts().to_string())
"""),
md(r"""
**Observation.** The data has no missing values and all columns are numeric, but **about 15% of rows are exact duplicates**. The target is ordinal and heavily concentrated: scores 5 and 6 account for over 80% of wines, while scores 3 and 8 together make up under 2%.
**Reason / impact.** Duplicates that land in both train and test leak information and inflate test scores, so they are removed **before** splitting. The concentration means a model can score a low MSE just by predicting about 5.6 for every wine. Splits are therefore stratified on the score, and metrics that reward getting the extremes right (QWK, R²) are reported alongside RMSE.

## 1.2 Comprehensive statistical analysis of feature distributions
"""),
code(r"""
def iqr_outliers(s):
    q1, q3 = s.quantile([.25, .75]); iqr = q3 - q1
    return int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())

stat_tbl = df_raw[FEATURES].describe().T
stat_tbl['cv'] = stat_tbl['std'] / stat_tbl['mean']
stat_tbl['skew'] = df_raw[FEATURES].skew()
stat_tbl['kurtosis'] = df_raw[FEATURES].kurt()
stat_tbl['normaltest_p'] = [stats.normaltest(df_raw[c])[1] for c in FEATURES]      # D'Agostino-Pearson
stat_tbl['outlier_%(IQR)'] = [100 * iqr_outliers(df_raw[c]) / len(df_raw) for c in FEATURES]
stat_tbl['spearman_vs_quality'] = [stats.spearmanr(df_raw[c], df_raw['quality'])[0] for c in FEATURES]
stat_tbl['kruskal_p(across scores)'] = [stats.kruskal(*[g[c].values for _, g in df_raw.groupby('quality')])[1] for c in FEATURES]
stat_tbl.sort_values('skew', ascending=False)
"""),
code(r"""
fig, axes = plt.subplots(3, 4, figsize=(16, 9.5))
for ax, c in zip(axes.ravel(), FEATURES):
    sns.histplot(df_raw[c], kde=True, ax=ax, color=PAL[0], alpha=.4)
    ax.set_title(f'{c}  (skew={df_raw[c].skew():.2f})', fontsize=10); ax.set_xlabel('')
ax = axes.ravel()[-1]; sns.histplot(df_raw['quality'], discrete=True, ax=ax, color=PAL[3]); ax.set_title('quality (target)', fontsize=10)
plt.suptitle('Figure 1.2a  Feature distributions', y=1.0, fontsize=14, weight='bold'); plt.tight_layout(); plt.show()

fig, axes = plt.subplots(3, 4, figsize=(16, 9.5))
for ax, c in zip(axes.ravel(), FEATURES):
    sns.boxplot(data=df_raw, x='quality', y=c, ax=ax, color=PAL[0], fliersize=2); ax.set_title(c, fontsize=10); ax.set_ylabel('')
axes.ravel()[-1].axis('off')
plt.suptitle('Figure 1.2b  Feature vs quality score (dots = IQR outliers)', y=1.0, fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
code(r"""
fig, ax = plt.subplots(1, 2, figsize=(17, 6.3), gridspec_kw={'width_ratios': [1.35, 1]})
corr = df_raw.corr(method='spearman')
sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool), 1), annot=True, fmt='.2f', cmap='RdBu_r', center=0,
            vmin=-1, vmax=1, ax=ax[0], annot_kws={'size': 8}, cbar_kws={'shrink': .7})
ax[0].set_title('Figure 1.2c  Spearman correlation matrix')
qc = corr['quality'].drop('quality').sort_values()
ax[1].barh(qc.index, qc.values, color=[PAL[3] if v > 0 else PAL[0] for v in qc.values]); ax[1].axvline(0, c='k', lw=.8)
ax[1].set_title('Figure 1.2d  Spearman correlation with quality'); plt.tight_layout(); plt.show()
"""),
md(r"""
**Statistical findings**
- **Non-normality (Observation).** Every feature rejects normality (D'Agostino–Pearson p ≪ 0.05). `chlorides`, `residual sugar`, `sulphates` and `total sulfur dioxide` are strongly right-skewed with heavy tails (chlorides has kurtosis ≈ 41). **Reason:** these quantities are bounded at zero and multiplicative in nature. **Impact:** skewed inputs push neurons into saturation and make some weights dominate, so a **Yeo–Johnson power transform** is used rather than plain standardisation.
- **Outliers.** IQR outliers affect up to about 7% of rows. They are chemically plausible (sweet or high-sulphate wines), not recording errors, so they are **kept** and down-weighted through the transform rather than deleted.
- **Signal.** `alcohol` has the strongest association with quality (ρ ≈ +0.48), followed by `volatile acidity` (ρ ≈ −0.38, the vinegar character of acetic acid), `sulphates` (+) and `citric acid` (+). The Kruskal–Wallis tests confirm these differ significantly across scores. `residual sugar` and `free sulfur dioxide` carry almost no signal.
- **Multicollinearity.** `fixed acidity`, `citric acid`, `density` and `pH` are inter-correlated (|ρ| ≈ 0.5–0.7), as acid chemistry would predict. This motivates the redundancy filter in Section 1.6.

## 1.3 Domain-driven feature engineering
Every engineered feature is a **row-wise** function of that wine's own measurements, so it cannot leak information between splits.

| Feature | Formula | Domain rationale |
|---|---|---|
| `total_acidity` | fixed + volatile + citric | overall perceived sourness |
| `fixed_to_volatile` | fixed / volatile | tartaric ("good") acid vs acetic (spoilage) acid |
| `free_so2_ratio` | free SO₂ / total SO₂ | share of SO₂ that is still active |
| `molecular_so2` | free SO₂ / (1 + 10^(pH − 1.81)) | the antimicrobial molecular form depends on pH (pKa ≈ 1.81); winemakers target about 0.5–0.8 mg/L |
| `bound_so2` | total − free SO₂ | SO₂ bound to acetaldehyde; an oxidation marker |
| `alcohol_x_sulphates` | alcohol × sulphates | interaction of the two strongest positive signals |
| `sugar_to_alcohol` | residual sugar / alcohol | completeness of fermentation / sweetness balance |
| `acid_to_alcohol` | total acidity / alcohol | the structural balance between acid and alcohol |
| `alcohol_band` *(categorical)* | low < 10% ≤ medium < 11.5% ≤ high | a wine-trade style band, used to demonstrate categorical encoding |
"""),
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
    d['alcohol_band'] = pd.cut(d['alcohol'], [0, 10, 11.5, 100], right=False, labels=['low', 'medium', 'high']).astype(str)
    return d

df = engineer_features(df_raw.drop_duplicates().reset_index(drop=True))   # de-duplicate BEFORE splitting
print(f'Rows after de-duplication: {len(df)} (removed {len(df_raw) - len(df)})')
ENG = ['total_acidity', 'fixed_to_volatile', 'free_so2_ratio', 'molecular_so2', 'bound_so2',
       'alcohol_x_sulphates', 'sugar_to_alcohol', 'acid_to_alcohol']
NUMERIC, CATEGORICAL = FEATURES + ENG, ['alcohol_band']

sig = pd.DataFrame({'spearman_vs_quality': [stats.spearmanr(df[c], df['quality'])[0] for c in NUMERIC],
                    'type': ['original'] * len(FEATURES) + ['engineered'] * len(ENG)}, index=NUMERIC)
sig['abs_rho'] = sig['spearman_vs_quality'].abs()
display(sig.sort_values('abs_rho', ascending=False).head(10))
print(df.groupby('alcohol_band')['quality'].agg(['count', 'mean']).reindex(['low', 'medium', 'high']).round(3))
"""),
md(r"""
**Observation.** `alcohol_x_sulphates` correlates with quality **more strongly than either parent feature** (it ranks first), and `fixed_to_volatile` beats `volatile acidity` alone. **Reason:** good wines combine ripeness (alcohol) with sound preservation (sulphates) and low acetic spoilage, and these ratios encode that combination directly. **Impact:** the network gets a head start on interactions it would otherwise have to learn from very little data. The `alcohol_band` table shows a steep gradient in mean quality, which Part 5 revisits as a possible source of bias.

## 1.4 Stratified train / validation / test split (70 / 15 / 15)
The split is stratified on the quality score, so every split keeps the same share of each score, including the rare 3s and 8s.
"""),
code(r"""
idx = np.arange(len(df))
tr_idx, tmp_idx = train_test_split(idx, test_size=0.30, stratify=df['quality'], random_state=SEED)
va_idx, te_idx = train_test_split(tmp_idx, test_size=0.50, stratify=df['quality'].iloc[tmp_idx], random_state=SEED)
df_tr, df_va, df_te = df.iloc[tr_idx], df.iloc[va_idx], df.iloc[te_idx]
y_train, y_val, y_test = (d['quality'].values.astype('float32') for d in (df_tr, df_va, df_te))
pd.DataFrame({n: {'n': len(d), 'mean_quality': d['quality'].mean(), **{f'share q={k}': (d['quality'] == k).mean()
             for k in sorted(df.quality.unique())}} for n, d in [('train', df_tr), ('validation', df_va), ('test', df_te)]}).T
"""),
md(r"""
## 1.5 Advanced preprocessing: transformation, scaling and encoding (fit on train only)
- **Numeric:** `PowerTransformer('yeo-johnson', standardize=True)`. This removes skew, then centres and scales each feature, and it handles zeros such as `citric acid = 0`, which Box–Cox and log transforms cannot.
- **Categorical:** `OneHotEncoder(handle_unknown='ignore')` for `alcohol_band`.
- Both transformers are fit on **train only** and then applied to validation and test, so no information leaks from the held-out data.
"""),
code(r"""
def make_preprocessor():
    return ColumnTransformer([('num', PowerTransformer(method='yeo-johnson', standardize=True), NUMERIC),
                              ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CATEGORICAL)])

pre = make_preprocessor().fit(df_tr)
ALL_FEATS = NUMERIC + [f'alcohol_band_{c}' for c in pre.named_transformers_['cat'].categories_[0]]
to_df = lambda d, p=pre: pd.DataFrame(p.transform(d), columns=ALL_FEATS, index=d.index)
Xtr_df, Xva_df, Xte_df = to_df(df_tr), to_df(df_va), to_df(df_te)

skew_cmp = pd.DataFrame({'before': df_tr[NUMERIC].skew(), 'after': Xtr_df[NUMERIC].skew()})
ax = skew_cmp.plot.bar(figsize=(13, 3.8), color=[PAL[1], PAL[2]]); ax.axhline(0, c='k', lw=.8)
ax.set_title('Figure 1.5  Skewness before vs after Yeo-Johnson (train)'); plt.xticks(rotation=60, ha='right'); plt.tight_layout(); plt.show()
print(f"Mean |skew| before = {skew_cmp['before'].abs().mean():.2f}, after = {skew_cmp['after'].abs().mean():.2f}")
"""),
md(r"""
## 1.6 Feature selection
A three-stage procedure, run on the training set only:
1. **Relevance:** mutual information with the quality score, which captures non-linear dependence.
2. **Redundancy:** for every pair with |r| > 0.85, drop the member with the lower mutual information.
3. **Embedded check:** an L1 (lasso) regression. A feature is kept if it survives step 2 **and** shows relevance (MI ≥ 0.01 **or** a non-zero lasso coefficient).

The result is checked against a ridge-regression baseline on the validation set, and multicollinearity is measured with the variance inflation factor (VIF).
"""),
code(r"""
mi = pd.Series(mutual_info_regression(Xtr_df, y_train, random_state=SEED,
               discrete_features=[c.startswith('alcohol_band') for c in ALL_FEATS]), index=ALL_FEATS)
l1 = pd.Series(Lasso(alpha=0.01, max_iter=20000).fit(Xtr_df, y_train).coef_, index=ALL_FEATS)
cabs = Xtr_df.corr().abs(); redundant = set()
for i, a in enumerate(ALL_FEATS):
    for b in ALL_FEATS[i + 1:]:
        if cabs.loc[a, b] > 0.85 and not {a, b} & redundant:
            redundant.add(a if mi[a] < mi[b] else b)
SELECTED = [f for f in ALL_FEATS if f not in redundant and (mi[f] >= 0.01 or abs(l1[f]) > 1e-6)]

vif = lambda X: pd.Series(np.diag(np.linalg.pinv(np.corrcoef(X, rowvar=False))), index=X.columns)
num_all = [c for c in ALL_FEATS if not c.startswith('alcohol_band')]
num_sel = [c for c in SELECTED if not c.startswith('alcohol_band')]
sel = pd.DataFrame({'mutual_info': mi, 'lasso_coef': l1, 'redundant': [f in redundant for f in ALL_FEATS],
                    'selected': [f in SELECTED for f in ALL_FEATS],
                    'VIF_all': vif(Xtr_df[num_all]).reindex(ALL_FEATS), 'VIF_selected': vif(Xtr_df[num_sel]).reindex(ALL_FEATS)})
display(sel.sort_values('mutual_info', ascending=False))
print(f'Selected {len(SELECTED)}/{len(ALL_FEATS)}:', SELECTED)
print('Dropped (redundant):', sorted(redundant), '| dropped (irrelevant):', sorted(set(ALL_FEATS) - set(SELECTED) - redundant))

def ridge_val_rmse(cols):
    m = Ridge(1.0).fit(Xtr_df[cols], y_train); return mean_squared_error(y_val, m.predict(Xva_df[cols])) ** .5
print(f'Ridge validation RMSE | 11 original: {ridge_val_rmse(FEATURES):.4f} | all {len(ALL_FEATS)}: '
      f'{ridge_val_rmse(ALL_FEATS):.4f} | selected {len(SELECTED)}: {ridge_val_rmse(SELECTED):.4f}')
"""),
code(r"""
X_train, X_val, X_test = (d[SELECTED].values.astype('float32') for d in (Xtr_df, Xva_df, Xte_df))
N_FEAT, Y_MEAN = X_train.shape[1], float(y_train.mean())

def reg_metrics(y, p):
    p = np.asarray(p, dtype='float64').ravel()
    if not np.all(np.isfinite(p)):
        return dict(rmse=np.nan, mae=np.nan, r2=np.nan, qwk=np.nan, exact=np.nan, within1=np.nan, good_auc=np.nan)
    r = np.clip(np.rint(p), 3, 8).astype(int); yi = y.astype(int)
    return dict(rmse=mean_squared_error(y, p) ** .5, mae=mean_absolute_error(y, p), r2=r2_score(y, p),
                qwk=cohen_kappa_score(yi, r, weights='quadratic'), exact=float(np.mean(r == yi)),
                within1=float(np.mean(np.abs(r - yi) <= 1)), good_auc=roc_auc_score(yi >= 7, p))

BASELINES = {'Predict train mean': reg_metrics(y_val, np.full_like(y_val, Y_MEAN))}
for n, m in [('Ridge regression', Ridge(1.0)),
             ('Random forest (500 trees)', RandomForestRegressor(500, min_samples_leaf=2, random_state=SEED, n_jobs=-1))]:
    BASELINES[n] = reg_metrics(y_val, m.fit(X_train, y_train).predict(X_val))
print('X_train', X_train.shape, 'X_val', X_val.shape, 'X_test', X_test.shape)
pd.DataFrame(BASELINES).T
"""),
md(r"""
**Part 1 summary.** De-duplication leaves 1,359 unique wines, split 70/15/15 with stratification on the score. The skewed features are power-transformed, the band is one-hot encoded, and selection keeps a compact, low-VIF set of features. Predicting the mean scores an R² of exactly 0, which is the floor any network must beat. The random forest sets a strong classical reference to compare against.
"""),
]

# =============================================================================
# Part 2
# =============================================================================
P2_FILL = r"""
# Model builder function (template signature kept; extra options are used in Parts 2-4)
def make_activation(name, i):
    if name == 'relu':       return layers.ReLU(name=f'act_{i}')
    if name == 'leaky_relu': return layers.LeakyReLU(negative_slope=0.1, name=f'act_{i}')
    if name == 'elu':        return layers.ELU(name=f'act_{i}')
    return layers.Activation(name, name=f'act_{i}')            # swish, selu, tanh, sigmoid

def make_init(init):            # strings -> fresh Keras initialiser; callables are factories
    return keras.initializers.get(init) if isinstance(init, str) else init()

def make_reg(reg):
    if reg is None: return None
    kind, *v = reg
    return {'l1': lambda: regularizers.L1(v[0]), 'l2': lambda: regularizers.L2(v[0]),
            'l1l2': lambda: regularizers.L1L2(l1=v[0], l2=v[1])}[kind]()

def build_deep_model(input_dim, depth=3, units=64, activation='relu', init='he_normal', norm=None,
                     dropout=0.0, dropout_positions='all', input_dropout=0.0, reg=None):
    model = keras.Sequential(name=f'mlp_d{depth}')
    model.add(layers.Input(shape=(input_dim,)))
    if input_dropout: model.add(layers.Dropout(input_dropout, name='input_dropout'))
    for i in range(1, depth + 1):
        model.add(layers.Dense(units, kernel_initializer=make_init(init), kernel_regularizer=make_reg(reg),
                               use_bias=(norm != 'batch'), name=f'dense_{i}'))
        if norm == 'batch': model.add(layers.BatchNormalization(name=f'bn_{i}'))
        if norm == 'layer': model.add(layers.LayerNormalization(name=f'ln_{i}'))
        model.add(make_activation(activation, i))
        use_do = {'all': True, 'early': i <= depth // 2, 'late': i > depth // 2}[dropout_positions]
        if dropout > 0 and use_do: model.add(layers.Dropout(dropout, name=f'dropout_{i}'))
    # regression task: one linear unit; bias starts at the training mean so all models begin from the same baseline
    model.add(layers.Dense(1, bias_initializer=keras.initializers.Constant(Y_MEAN), name='output'))
    return model

# Custom callback to log gradients (GradientTape inside a tf.function)
class GradientNormCallback(keras.callbacks.Callback):
    # Records the L2 norm of dLoss/dKernel for every Dense layer on a fixed probe set,
    # once before training (epoch 0) and after every epoch.
    def __init__(self, X, y):
        super().__init__()
        self.X, self.y = tf.constant(X), tf.constant(np.asarray(y, 'float32').reshape(-1, 1))
        self.records, self.names, self._fn = [], None, None

    def _build(self):
        dense = [l for l in self.model.layers if isinstance(l, layers.Dense)]
        self.names, kernels, mse = [l.name for l in dense], [l.kernel for l in dense], keras.losses.MeanSquaredError()
        @tf.function
        def grad_norms(X, y):
            with tf.GradientTape() as tape:
                loss = mse(y, self.model(X, training=True))
            return [tf.norm(g) for g in tape.gradient(loss, kernels)]
        self._fn = grad_norms

    def _log(self):
        self.records.append([float(v) for v in self._fn(self.X, self.y)])

    def on_train_begin(self, logs=None):
        self._build(); self._log()
    def on_epoch_end(self, epoch, logs=None):
        self._log()
    def frame(self):            # rows: epoch (0 = initialisation); columns: dense_1 ... output
        return pd.DataFrame(self.records, columns=self.names)

class LRLogger(keras.callbacks.Callback):
    def on_train_begin(self, logs=None): self.lrs = []
    def on_epoch_end(self, epoch, logs=None): self.lrs.append(float(np.asarray(self.model.optimizer.learning_rate)))

def make_ds(X, y, batch_size=64, train=True):
    # cached tf.data pipeline (reshuffled every epoch) -- ~2-3x faster than feeding NumPy arrays to fit()
    ds = tf.data.Dataset.from_tensor_slices((X, np.asarray(y, 'float32'))).cache()
    if train: ds = ds.shuffle(len(X))
    return ds.batch(batch_size if train else 4096).prefetch(tf.data.AUTOTUNE)

def predict(model, X):          # direct call: much faster than model.predict() for small in-memory arrays
    return model(X, training=False).numpy().ravel()

VAL_DS = make_ds(X_val, y_val, train=False)
build_deep_model(N_FEAT, depth=3).summary()
"""

P2 = [
md(r"""
## 2.1 Experiment design: depths 3, 6, 9 and 12
`build_deep_model` (above) builds each hidden block as `Dense → [norm] → activation → [dropout]`, so activations can be probed by name. `GradientNormCallback` is the required **custom callback**: before training and after every epoch it runs `tf.GradientTape` (compiled with `tf.function`) on a fixed probe set, the whole training set. It logs ‖∂L/∂W‖ for every layer, from layer 1 (input side) to the output layer. Because the probe set is fixed, the measurements are free of mini-batch noise and comparable across epochs.

Each depth is trained in **three regimes**. Within a regime, depth is the only factor that changes.

| Regime | Activation | Initialisation | Hypothesis |
|---|---|---|---|
| A | sigmoid | Xavier/Glorot | **vanishing**: σ′ ≤ 0.25, so the gradient shrinks at least 4× per layer |
| B | ReLU | He normal | **healthy**: the derivative is 1 on active paths, and He scaling preserves variance |
| C | ReLU | N(0, 0.5²), about 2.8× He's std | **exploding**: variance grows about 8× per layer |

All runs use SGD with momentum (lr = 0.01, momentum = 0.9) for 40 epochs. Plain SGD is used deliberately: adaptive optimisers rescale gradients and would hide the raw magnitudes. `TerminateOnNaN` stops runs that diverge.
"""),
code(r"""
DEPTHS, EP_G = [3, 6, 9, 12], E(40)
REGIMES = {'A. sigmoid + Xavier': dict(activation='sigmoid', init='glorot_uniform'),
           'B. ReLU + He': dict(activation='relu', init='he_normal'),
           'C. ReLU + N(0,0.5)': dict(activation='relu', init=lambda: keras.initializers.RandomNormal(stddev=0.5))}

def grad_experiment(kw, depth, opt=None, extra=None, epochs=EP_G):
    keras.utils.set_random_seed(SEED)
    model = build_deep_model(N_FEAT, depth=depth, **kw, **(extra or {}))
    model.compile(optimizer=opt() if opt else keras.optimizers.SGD(0.01, momentum=0.9), loss='mse',
                  metrics=[keras.metrics.RootMeanSquaredError(name='rmse')], steps_per_execution=16)
    cb = GradientNormCallback(X_train, y_train)
    h = model.fit(make_ds(X_train, y_train), validation_data=VAL_DS, epochs=epochs, verbose=0,
                  callbacks=[cb, keras.callbacks.TerminateOnNaN()])
    return dict(grads=cb.frame(), hist=pd.DataFrame(h.history), val=reg_metrics(y_val, predict(model, X_val)),
                diverged=not np.isfinite(h.history['loss'][-1]), epochs=len(h.history['loss']))

t0 = time.time()
GR = {(r, d): grad_experiment(kw, d) for r, kw in REGIMES.items() for d in DEPTHS}
print(f'{len(GR)} runs in {time.time() - t0:.0f}s')
"""),
md(r"""
## 2.2 Visualising gradient flow through the layers
"""),
code(r"""
fig, axes = plt.subplots(2, 3, figsize=(17, 8.5), sharey='row')
for j, r in enumerate(REGIMES):
    for k, d in enumerate(DEPTHS):
        g = GR[(r, d)]['grads']; x = np.arange(1, g.shape[1] + 1)
        fin = g[np.isfinite(g).all(axis=1)]
        axes[0, j].semilogy(x, g.iloc[0], '-o', ms=4, color=PAL[k], label=f'{d} hidden layers')
        axes[1, j].semilogy(x, fin.iloc[-1], '-o', ms=4, color=PAL[k], label=f'{d} hidden layers')
    axes[0, j].set_title(f'{r}: at initialisation'); axes[1, j].set_title(f'{r}: end of training (last finite)')
    axes[1, j].set_xlabel('layer (1 = input side ... last = output)')
for a in axes[:, 0]: a.set_ylabel('||dL/dW|| (log)')
axes[0, 0].legend(fontsize=9)
plt.suptitle('Figure 2.2a  Layer-wise gradient-norm profile, by depth', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
code(r"""
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, r in zip(axes, REGIMES):
    g = GR[(r, 12)]['grads']
    sns.heatmap(np.log10(g.T.replace(0, np.nan).astype(float)), ax=ax, cmap='magma', cbar_kws={'label': 'log10 ||dL/dW||'},
                xticklabels=max(1, len(g) // 8))
    ax.set(title=f'{r}: 12 hidden layers', xlabel='epoch (0 = init)', ylabel='')
plt.suptitle('Figure 2.2b  Gradient magnitude by layer and epoch (deepest network)', fontsize=14, weight='bold')
plt.tight_layout(); plt.show()

fig, axes = plt.subplots(1, 3, figsize=(18, 4), sharey=True)
for ax, r in zip(axes, REGIMES):
    for k, d in enumerate(DEPTHS):
        ax.plot(GR[(r, d)]['hist']['val_rmse'], color=PAL[k], label=f'{d} layers')
    ax.axhline(BASELINES['Predict train mean']['rmse'], ls=':', c='grey', label='predict-mean RMSE')
    ax.set(title=f'{r}: validation RMSE', xlabel='epoch', ylim=(0.55, 1.0))
axes[0].legend(fontsize=8)
plt.suptitle('Figure 2.2c  Learning progress vs depth', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
## 2.3 Quantifying vanishing and exploding patterns
**Gradient ratio** = ‖∂L/∂W₁‖ / ‖∂L/∂W_last hidden‖ at initialisation. A ratio ≪ 1 means **vanishing** (early layers barely learn); a ratio ≈ 1 means **healthy** flow. Huge absolute norms, or a loss that turns to NaN, mean **exploding**. The **log₁₀ change per layer** gives the average rate of decay (negative) or growth (positive) as depth increases.
"""),
code(r"""
rows = []
for (r, d), res in GR.items():
    h = res['grads'].iloc[0].values[:-1]                      # hidden layers only, at initialisation
    rows.append({'regime': r, 'depth': d, 'grad_L1_init': h[0], 'grad_Llast_init': h[-1], 'ratio_first/last': h[0] / h[-1],
                 'log10_change_per_layer': np.log10(h[0] / h[-1]) / max(1, d - 1),
                 'max_grad_norm': np.nanmax(res['grads'].values), 'diverged': res['diverged'], 'epochs_run': res['epochs'],
                 'val_rmse': res['val']['rmse'], 'val_r2': res['val']['r2']})
GRAD_SUMMARY = pd.DataFrame(rows)
display(GRAD_SUMMARY.style.format({**{c: '{:.2e}' for c in ['grad_L1_init', 'grad_Llast_init', 'ratio_first/last', 'max_grad_norm']},
                                   'log10_change_per_layer': '{:+.3f}', 'val_rmse': '{:.4f}', 'val_r2': '{:.4f}'}))
fig, ax = plt.subplots(1, 3, figsize=(17, 4))
for k, r in enumerate(REGIMES):
    s = GRAD_SUMMARY[GRAD_SUMMARY.regime == r]
    ax[0].semilogy(s.depth, s['ratio_first/last'], '-o', color=PAL[k], label=r)
    ax[1].semilogy(s.depth, s['max_grad_norm'], '-o', color=PAL[k], label=r)
    ax[2].plot(s.depth, s['val_r2'].clip(lower=-0.5), '-o', color=PAL[k], label=r)
ax[0].axhline(1, ls=':', c='grey'); ax[0].set(title='Gradient ratio layer1/last at init', xlabel='hidden layers')
ax[1].set(title='Max gradient norm seen', xlabel='hidden layers')
ax[2].axhline(0, ls=':', c='grey'); ax[2].set(title='Validation R² (clipped at -0.5)', xlabel='hidden layers'); ax[0].legend(fontsize=8)
plt.suptitle('Figure 2.3  How gradients change with depth', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
## 2.4 Fixing the pathologies (12 hidden layers)
Each row applies **one remedy** to a failing 12-layer network: **gradient clipping** (`clipnorm=1`) or **BatchNorm** for the exploding regime C, and **BatchNorm** for the vanishing regime A.
"""),
code(r"""
FIXES = {'C. no fix': ('C. ReLU + N(0,0.5)', None, None),
         'C + gradient clipping (clipnorm=1)': ('C. ReLU + N(0,0.5)', lambda: keras.optimizers.SGD(0.01, momentum=0.9, clipnorm=1.0), None),
         'C + BatchNorm': ('C. ReLU + N(0,0.5)', None, dict(norm='batch')),
         'A. no fix': ('A. sigmoid + Xavier', None, None),
         'A + BatchNorm': ('A. sigmoid + Xavier', None, dict(norm='batch'))}
FIX = {n: (GR[(r, 12)] if (o is None and e is None) else grad_experiment(REGIMES[r], 12, o, e)) for n, (r, o, e) in FIXES.items()}
fig, ax = plt.subplots(1, 2, figsize=(15, 4.3))
for k, (n, res) in enumerate(FIX.items()):
    g = res['grads']; ax[0].semilogy(np.arange(1, g.shape[1] + 1), g.iloc[0], '-o', ms=4, color=PAL[k], label=n)
    ax[1].plot(res['hist']['val_rmse'], color=PAL[k], label=n)
ax[0].set(title='Gradient profile at initialisation', xlabel='layer'); ax[0].legend(fontsize=8)
ax[1].set(title='Validation RMSE', xlabel='epoch', ylim=(0.55, 1.0))
plt.suptitle('Figure 2.4  Remedies for exploding / vanishing gradients (12 layers)', fontsize=14, weight='bold')
plt.tight_layout(); plt.show()
pd.DataFrame({n: {'diverged': r['diverged'], 'epochs_run': r['epochs'], 'max_grad_norm': np.nanmax(r['grads'].values),
                  'val_rmse': r['val']['rmse'], 'val_r2': r['val']['r2']} for n, r in FIX.items()}).T
"""),
md(r"""
<!--INTERP_PART2-->
"""),
]

# =============================================================================
# Part 3
# =============================================================================
P3_FILL = r"""
# Shared experiment harness: one call = one configuration trained under every seed in SEEDS
def run_config(name, model_kw=None, opt_fn=lambda: keras.optimizers.Adam(1e-3), seeds=None, epochs=None,
               early_stop=True, patience=15, monitor='val_loss', restore=True, callbacks_fn=None,
               grads=False, X_tr=None, y_tr=None, batch_size=64):
    seeds, epochs = seeds or SEEDS, epochs or E(100)
    X_tr = X_train if X_tr is None else X_tr; y_tr = y_train if y_tr is None else y_tr
    runs = []
    for s in seeds:
        keras.utils.set_random_seed(s)
        model = build_deep_model(N_FEAT, **{'depth': 4, **(model_kw or {})})
        model.compile(optimizer=opt_fn(), loss='mse', metrics=[keras.metrics.RootMeanSquaredError(name='rmse'), 'mae'],
                      steps_per_execution=16)
        lr_cb = LRLogger(); cbs = [keras.callbacks.TerminateOnNaN(), lr_cb]
        if early_stop:
            cbs.append(keras.callbacks.EarlyStopping(monitor=monitor, patience=patience, restore_best_weights=restore))
        gcb = GradientNormCallback(X_tr, y_tr) if (grads and s == seeds[0]) else None
        if gcb: cbs.append(gcb)
        if callbacks_fn: cbs += callbacks_fn()
        t = time.time()
        h = model.fit(make_ds(X_tr, y_tr, batch_size), validation_data=VAL_DS, epochs=epochs, verbose=0, callbacks=cbs)
        hist = pd.DataFrame(h.history); hist['lr'] = lr_cb.lrs[:len(hist)]
        vl = hist['val_loss'].replace([np.inf, -np.inf], np.nan)
        runs.append(dict(seed=s, model=model, hist=hist, grads=gcb.frame() if gcb else None, time=time.time() - t,
                         epochs_run=len(hist), best_epoch=int(vl.idxmin()) + 1 if vl.notna().any() else np.nan,
                         **{f'val_{k}': v for k, v in reg_metrics(y_val, predict(model, X_val)).items()},
                         **{f'train_{k}': v for k, v in reg_metrics(y_tr, predict(model, X_tr)).items()}))
    return dict(name=name, runs=runs)

def summarise(results):
    cols = ['val_rmse', 'val_mae', 'val_r2', 'val_qwk', 'val_within1', 'val_good_auc', 'train_rmse', 'best_epoch', 'epochs_run', 'time']
    out = {}
    for r in results:
        d = pd.DataFrame([{c: run[c] for c in cols} for run in r['runs']])
        out[r['name']] = {**d.mean().to_dict(), 'val_rmse_std': d['val_rmse'].std()}
    t = pd.DataFrame(out).T
    t['gap(val-train RMSE)'] = t['val_rmse'] - t['train_rmse']
    return t[['val_rmse', 'val_rmse_std', 'val_mae', 'val_r2', 'val_qwk', 'val_within1', 'val_good_auc', 'train_rmse',
              'gap(val-train RMSE)', 'best_epoch', 'epochs_run', 'time']]

def curves(results, metric, ax, title, ylim=None):
    for k, r in enumerate(results):
        for j, run in enumerate(r['runs']):
            ax.plot(run['hist'][metric].values, color=PAL[k % 10], alpha=1 if j == 0 else .3, label=r['name'] if j == 0 else None)
    ax.set(title=title, xlabel='epoch');  ax.set_ylim(ylim) if ylim else None

def bars(summary, ax, title):
    s = summary.sort_values('val_rmse', ascending=False)
    ax.barh(s.index, s['val_rmse'], xerr=s['val_rmse_std'].fillna(0), color=PAL[0], alpha=.8, capsize=3)
    lo = np.nanmin(s['val_rmse']) - 0.03; ax.set_xlim(lo, min(np.nanmax(s['val_rmse']) + .03, 1.2))
    for i, v in enumerate(s['val_rmse']): ax.text(min(v, 1.19) + .002, i, f'{v:.3f}', va='center', fontsize=9)
    ax.set(title=title, xlabel='validation RMSE (lower is better; mean ± std)')

BASE = dict(depth=4, units=64, activation='relu', init='he_normal')     # Part-3 baseline architecture

# Loop over optimizers (Section 3.1)
OPTS = {'SGD (0.01)': lambda: keras.optimizers.SGD(0.01),
        'SGD + Nesterov momentum (0.01)': lambda: keras.optimizers.SGD(0.01, momentum=0.9, nesterov=True),
        'Adam (1e-3)': lambda: keras.optimizers.Adam(1e-3),
        'RMSprop (1e-3)': lambda: keras.optimizers.RMSprop(1e-3),
        'AdaGrad (0.05)': lambda: keras.optimizers.Adagrad(0.05)}
OPT_RES = [run_config(n, BASE, f) for n, f in OPTS.items()]
OPT_SUM = summarise(OPT_RES); display(OPT_SUM)
fig, ax = plt.subplots(1, 3, figsize=(19, 4.3))
curves(OPT_RES, 'loss', ax[0], 'Training MSE', (0.2, 1.0)); ax[0].legend(fontsize=8)
curves(OPT_RES, 'val_loss', ax[1], 'Validation MSE', (0.3, 0.8)); bars(OPT_SUM, ax[2], 'Validation RMSE by optimiser')
plt.suptitle('Figure 3.1a  Optimiser comparison (baseline: ReLU + He, 4x64)', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""

P3 = [
md(r"""
## 3.1 Optimisers: SGD, SGD + Momentum, Adam, RMSprop and AdaGrad
The cell above trains the baseline network (4 × 64, ReLU + He) with each optimiser at a conventional learning rate (Figure 3.1a). Comparing optimisers at one learning rate each is biased, because every optimiser has its own good range. The sweep below therefore varies the learning rate as the single extra factor (Figure 3.1b).
"""),
code(r"""
LRS = [1e-3, 1e-2, 1e-1]
OPT_LR = {'SGD+Momentum': lambda lr: keras.optimizers.SGD(lr, momentum=0.9), 'Adam': lambda lr: keras.optimizers.Adam(lr),
          'RMSprop': lambda lr: keras.optimizers.RMSprop(lr), 'AdaGrad': lambda lr: keras.optimizers.Adagrad(lr)}
sens = pd.DataFrame(index=list(OPT_LR), columns=LRS, dtype=float)
for o, f in OPT_LR.items():
    for lr in LRS:
        sens.loc[o, lr] = run_config(f'{o}@{lr}', BASE, (lambda f=f, lr=lr: f(lr)), seeds=[SEED], epochs=E(60), patience=10)['runs'][0]['val_rmse']
plt.figure(figsize=(7, 3.3)); sns.heatmap(sens.clip(upper=1.2), annot=sens.round(3), fmt='', cmap='viridis_r', cbar_kws={'label': 'val RMSE'})
plt.title('Figure 3.1b  Optimiser x learning-rate (val RMSE)'); plt.xlabel('learning rate'); plt.show()
"""),
md(r"""
<!--INTERP_OPT-->

## 3.2 Weight-initialisation strategies
**One factor:** the initialiser. Fixed: 6 hidden layers, ReLU, SGD + momentum (Adam would partly mask a poor initial scale). Compared: **Xavier/Glorot** uniform and normal (Var = 2/(fan_in + fan_out)), **He** normal and uniform (Var = 2/fan_in, derived for ReLU), **LeCun** normal (Var = 1/fan_in), a too-small N(0, 0.01²), a too-large N(0, 1), and **zeros**. Before any training, the **forward signal** is also measured: the standard deviation of each layer's activations.
"""),
code(r"""
INITS = {'Xavier uniform': 'glorot_uniform', 'Xavier normal': 'glorot_normal', 'He normal': 'he_normal', 'He uniform': 'he_uniform',
         'LeCun normal': 'lecun_normal', 'Small N(0,0.01)': lambda: keras.initializers.RandomNormal(stddev=0.01),
         'Large N(0,1)': lambda: keras.initializers.RandomNormal(stddev=1.0), 'Zeros': 'zeros'}
SGDM = lambda: keras.optimizers.SGD(0.01, momentum=0.9)

def act_outputs(model, X):
    outs = keras.Model(model.inputs, [l.output for l in model.layers if l.name.startswith('act_')])(X, training=False)
    return [o.numpy() for o in outs]

act_std = {}
for n, i in INITS.items():
    keras.utils.set_random_seed(SEED); act_std[n] = [float(np.std(a)) for a in act_outputs(build_deep_model(N_FEAT, 6, init=i), X_train)]
INIT_RES = [run_config(n, dict(depth=6, init=i), SGDM, grads=True) for n, i in INITS.items()]
INIT_SUM = summarise(INIT_RES); display(INIT_SUM)
fig, ax = plt.subplots(1, 3, figsize=(19, 4.5))
for k, r in enumerate(INIT_RES):
    ax[0].semilogy(range(1, 7), np.maximum(act_std[r['name']], 1e-12), '-o', ms=4, color=PAL[k], label=r['name'])
    g = r['runs'][0]['grads']; ax[1].semilogy(range(1, g.shape[1] + 1), np.maximum(g.iloc[0], 1e-12), '-o', ms=4, color=PAL[k])
ax[0].set(title='Forward: activation std per layer (init)', xlabel='hidden layer'); ax[0].legend(fontsize=7)
ax[1].set(title='Backward: ||dL/dW|| per layer (init)', xlabel='layer (last = output)'); bars(INIT_SUM, ax[2], 'Validation RMSE by initialiser')
plt.suptitle('Figure 3.2  Weight initialisation (6 layers, ReLU, SGD+momentum)', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_INIT-->

## 3.3 Activation functions: ReLU, Leaky ReLU, ELU and Swish
**One factor:** the activation. Fixed: 6 × 64, He initialisation, Adam 1e-3. Tanh with Xavier is included as a classic reference. After training, **dead units** are counted: hidden units whose output is ≤ 0 for every training example, so they pass no gradient (the "dying ReLU" problem).
"""),
code(r"""
xs = np.linspace(-4, 4, 400); sg = 1 / (1 + np.exp(-xs))
FNS = {'ReLU': (np.maximum(0, xs), (xs > 0) * 1.), 'Leaky ReLU (0.1)': (np.where(xs > 0, xs, .1 * xs), np.where(xs > 0, 1, .1)),
       'ELU': (np.where(xs > 0, xs, np.exp(xs) - 1), np.where(xs > 0, 1, np.exp(xs))), 'Swish': (xs * sg, sg * (1 + xs * (1 - sg))),
       'tanh': (np.tanh(xs), 1 - np.tanh(xs) ** 2), 'sigmoid': (sg, sg * (1 - sg))}
fig, ax = plt.subplots(1, 2, figsize=(14, 3.6))
for k, (n, (f, d)) in enumerate(FNS.items()):
    ax[0].plot(xs, f, color=PAL[k], label=n); ax[1].plot(xs, d, color=PAL[k], label=n)
ax[0].set(title='f(x)', ylim=(-1.5, 4)); ax[1].set(title="f'(x): the factor multiplying the backward gradient"); ax[0].legend(fontsize=8)
plt.suptitle('Figure 3.3a  Activation functions and their derivatives', fontsize=13, weight='bold'); plt.tight_layout(); plt.show()

ACTS = {'ReLU': ('relu', 'he_normal'), 'Leaky ReLU (0.1)': ('leaky_relu', 'he_normal'), 'ELU': ('elu', 'he_normal'),
        'Swish': ('swish', 'he_normal'), 'tanh (+Xavier)': ('tanh', 'glorot_uniform')}
ACT_RES = [run_config(n, dict(depth=6, activation=a, init=i), grads=True) for n, (a, i) in ACTS.items()]
ACT_SUM = summarise(ACT_RES)
dead = {r['name']: 100 * np.mean([np.mean(np.concatenate([o.max(0) <= 1e-8 for o in act_outputs(run['model'], X_train)]))
                                   for run in r['runs']]) for r in ACT_RES}
ACT_SUM['dead_units_%'] = pd.Series(dead); display(ACT_SUM)
fig, ax = plt.subplots(1, 3, figsize=(19, 4.3))
curves(ACT_RES, 'val_loss', ax[0], 'Validation MSE', (0.3, 0.8)); ax[0].legend(fontsize=8)
for k, r in enumerate(ACT_RES):
    g = r['runs'][0]['grads']; ax[1].semilogy(range(1, g.shape[1] + 1), g.iloc[0], '-o', ms=4, color=PAL[k], label=r['name'])
ax[1].set(title='Gradient profile at init', xlabel='layer'); bars(ACT_SUM, ax[2], 'Validation RMSE by activation')
plt.suptitle('Figure 3.3b  Activation comparison (6 layers, Adam)', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_ACT-->

## 3.4 Batch normalisation and layer normalisation
**One factor:** the normalisation layer (none, BatchNorm or LayerNorm), tested in two settings:
- **(a) Rescue:** a 9-layer **sigmoid** network with SGD + momentum, which suffers vanishing gradients in Part 2.
- **(b) Modern:** a 6-layer ReLU network with Adam, where gradients are already healthy.

BatchNorm normalises each unit across the **mini-batch** and keeps running statistics for inference. LayerNorm normalises across the **features of each sample**, so it behaves the same at training and inference time and does not depend on batch size.
"""),
code(r"""
NORMS = [('no norm', None), ('BatchNorm', 'batch'), ('LayerNorm', 'layer')]
NORM_A = [run_config(f'sigmoid-9 | {n}', dict(depth=9, activation='sigmoid', init='glorot_uniform', norm=v), SGDM, grads=True) for n, v in NORMS]
NORM_B = [run_config(f'ReLU-6 | {n}', dict(depth=6, norm=v), grads=True) for n, v in NORMS]
NORM_SUM = summarise(NORM_A + NORM_B); display(NORM_SUM)
fig, ax = plt.subplots(1, 4, figsize=(22, 4.3))
for k, r in enumerate(NORM_A):
    g = r['runs'][0]['grads']; ax[0].semilogy(range(1, g.shape[1] + 1), g.iloc[0], '-o', ms=4, color=PAL[k], label=r['name'])
curves(NORM_A, 'val_rmse', ax[1], '(a) sigmoid-9: validation RMSE', (0.55, 1.0)); curves(NORM_B, 'val_rmse', ax[2], '(b) ReLU-6: validation RMSE', (0.55, 0.9))
ax[0].set(title='(a) sigmoid-9: gradient profile at init', xlabel='layer'); ax[0].legend(fontsize=8); ax[1].legend(fontsize=8); ax[2].legend(fontsize=8)
bars(NORM_SUM, ax[3], 'Validation RMSE by normalisation')
plt.suptitle('Figure 3.4  Batch vs Layer normalisation', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_NORM-->

## 3.5 Learning-rate scheduling
**One factor:** the schedule. Fixed: the baseline network, SGD + momentum with a peak learning rate of 0.01 (the SGD + momentum value from 3.1), and 60 epochs **without** early stopping (early stopping would cut decaying schedules short).

| Schedule | Definition |
|---|---|
| Constant | lr = 0.01 throughout |
| Step decay | halve every 15 epochs (`LearningRateScheduler`) |
| Exponential decay | ×0.95 per epoch, applied per step (`ExponentialDecay`) |
| Cosine + warm-up | 5-epoch linear warm-up, then cosine decay to 0 (`CosineDecay(warmup_target=...)`) |
| ReduceLROnPlateau | halve when validation loss stalls for 4 epochs |
"""),
code(r"""
LR0, EP_S, STEPS = 0.01, E(60), math.ceil(len(X_train) / 64)
SCHED = {
    'Constant': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9)),
    'Step decay (x0.5/15 ep)': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9),
        callbacks_fn=lambda: [keras.callbacks.LearningRateScheduler(lambda ep, lr: LR0 * 0.5 ** (ep // 15))]),
    'Exponential decay': dict(opt_fn=lambda: keras.optimizers.SGD(keras.optimizers.schedules.ExponentialDecay(LR0, STEPS, 0.95), momentum=0.9)),
    'Cosine + warm-up': dict(opt_fn=lambda: keras.optimizers.SGD(keras.optimizers.schedules.CosineDecay(
        0.0, STEPS * (EP_S - 5), warmup_target=LR0, warmup_steps=STEPS * 5), momentum=0.9)),
    'ReduceLROnPlateau': dict(opt_fn=lambda: keras.optimizers.SGD(LR0, momentum=0.9),
        callbacks_fn=lambda: [keras.callbacks.ReduceLROnPlateau('val_loss', factor=0.5, patience=4, min_lr=1e-5)])}
SCHED_RES = [run_config(n, BASE, epochs=EP_S, early_stop=False, **kw) for n, kw in SCHED.items()]
SCHED_SUM = summarise(SCHED_RES)
SCHED_SUM['best_val_rmse_any_epoch'] = [np.mean([run['hist']['val_rmse'].min() for run in r['runs']]) for r in SCHED_RES]
SCHED_SUM['val_rmse_last5_std'] = [np.mean([run['hist']['val_rmse'].iloc[-5:].std() for run in r['runs']]) for r in SCHED_RES]
display(SCHED_SUM[['val_rmse', 'val_rmse_std', 'best_val_rmse_any_epoch', 'val_rmse_last5_std', 'val_r2', 'val_qwk', 'train_rmse', 'gap(val-train RMSE)']])
fig, ax = plt.subplots(1, 3, figsize=(19, 4.3))
for k, r in enumerate(SCHED_RES):
    h = r['runs'][0]['hist']; ax[0].plot(h['lr'], color=PAL[k], label=r['name'])
    ax[1].plot(h['val_rmse'], color=PAL[k]); ax[2].plot(h['rmse'], color=PAL[k])
ax[0].set(title='Learning rate', xlabel='epoch', yscale='log'); ax[0].legend(fontsize=8)
ax[1].set(title='Validation RMSE', xlabel='epoch', ylim=(0.55, 0.9)); ax[2].set(title='Training RMSE', xlabel='epoch', ylim=(0.2, 0.9))
plt.suptitle('Figure 3.5  Learning-rate schedules (SGD+momentum, peak lr 0.01)', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_SCHED-->

## 3.6 Combining the evidence: tuned configuration vs baseline
The individually best choices from Sections 3.1–3.5 are combined. Because this changes several factors at once, it is presented as a **confirmation** run against the Part 3 baseline, not as an attribution experiment.
"""),
code(r"""
# Evidence used: 3.1 SGD+Nesterov among the best optimisers | 3.2 He init (matched to the ReLU family, stable across seeds)
#                3.3 Swish best ReLU-family activation, no dead units | 3.4 LayerNorm best in the ReLU-6 setting
#                3.5 ReduceLROnPlateau best final val RMSE and smallest gap
TUNED = dict(depth=4, units=64, activation='swish', init='he_normal', norm='layer')
TUNED_OPT = lambda: keras.optimizers.SGD(0.01, momentum=0.9, nesterov=True)
PLATEAU = lambda: [keras.callbacks.ReduceLROnPlateau('val_loss', factor=0.5, patience=4, min_lr=1e-5)]
COMBO = [run_config('Baseline: ReLU + He + Adam(1e-3)', BASE),
         run_config('Tuned: Swish + He + LayerNorm, SGD-Nesterov + ReduceLROnPlateau', TUNED, TUNED_OPT, callbacks_fn=PLATEAU, patience=20)]
COMBO_SUM = summarise(COMBO); display(COMBO_SUM)
fig, ax = plt.subplots(1, 2, figsize=(14, 3.8))
curves(COMBO, 'val_rmse', ax[0], 'Validation RMSE', (0.55, 0.85)); curves(COMBO, 'rmse', ax[1], 'Training RMSE', (0.2, 0.85)); ax[0].legend(fontsize=8)
plt.suptitle('Figure 3.6  Baseline vs tuned configuration', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_COMBO-->
"""),
]

# =============================================================================
# Part 4
# =============================================================================
P4_FILL = r"""
# Regularization examples: L1, L2 and Elastic Net on a deliberately over-parameterised network
# (4 x 128, Adam 1e-3, 100 epochs, no early stopping) so that overfitting -- and its cure -- is visible.
OVERFIT = dict(depth=4, units=128)
EP_R = E(100)

def weight_stats(model):
    w = np.concatenate([l.kernel.numpy().ravel() for l in model.layers if isinstance(l, layers.Dense)])
    return dict(w_l2=float(np.linalg.norm(w)), w_sparsity_pct=float(100 * np.mean(np.abs(w) < 1e-3)))

def run_reg(name, seeds=None, **kw):
    r = run_config(name, {**OVERFIT, **kw.pop('model_kw', {})}, epochs=kw.pop('epochs', EP_R),
                   early_stop=kw.pop('early_stop', False), seeds=seeds or [SEED], **kw)
    for run in r['runs']:
        run.update(weight_stats(run['model'])); run['min_val_rmse'] = run['hist']['val_rmse'].min()
    return r

def reg_table(results):
    t = summarise(results)
    extra = pd.DataFrame({r['name']: {k: np.mean([x[k] for x in r['runs']]) for k in ('min_val_rmse', 'w_l2', 'w_sparsity_pct')} for r in results}).T
    return t[['val_rmse', 'val_mae', 'val_r2', 'val_qwk', 'train_rmse', 'gap(val-train RMSE)']].join(extra)

REG_RES = [run_reg('No regularisation', seeds=SEEDS),
           run_reg('L1 (1e-4)', seeds=SEEDS, model_kw=dict(reg=('l1', 1e-4))),
           run_reg('L2 (1e-3)', seeds=SEEDS, model_kw=dict(reg=('l2', 1e-3))),
           run_reg('Elastic net (L1 5e-5 + L2 5e-4)', seeds=SEEDS, model_kw=dict(reg=('l1l2', 5e-5, 5e-4)))]
REG_SUM = reg_table(REG_RES); display(REG_SUM)
fig, axes = plt.subplots(1, 5, figsize=(24, 4))
for ax, r in zip(axes, REG_RES):
    h = r['runs'][0]['hist']; ax.plot(h['rmse'], label='train'); ax.plot(h['val_rmse'], label='validation')
    ax.set(title=r['name'], xlabel='epoch', ylim=(0, 1.0))
axes[0].legend(); axes[0].set_ylabel('RMSE')
for k, r in enumerate(REG_RES):
    w = np.concatenate([l.kernel.numpy().ravel() for l in r['runs'][0]['model'].layers if isinstance(l, layers.Dense)])
    axes[4].hist(w, bins=150, range=(-.4, .4), histtype='step', lw=1.5, color=PAL[k], density=True, label=r['name'])
axes[4].set(title='Weight distributions', yscale='log'); axes[4].legend(fontsize=7)
plt.suptitle('Figure 4.1a  Learning curves and weights under L1 / L2 / Elastic-net', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()

# Dropout and early stopping -> sections 4.2 and 4.3 below
"""

P4 = [
md(r"""
### 4.1b Validation curve: L2 strength (λ)
A validation curve sweeps one complexity control. A λ that is too small leaves **high variance** (a large train–validation gap); a λ that is too large causes **high bias** (both errors rise).
"""),
code(r"""
L2_GRID = [0, 1e-4, 1e-3, 1e-2, 1e-1]
VC = reg_table([run_reg(f'L2={l:g}', model_kw=dict(reg=('l2', l) if l else None)) for l in L2_GRID])
xs_ = [1e-5] + L2_GRID[1:]
fig, ax = plt.subplots(figsize=(8, 3.8))
ax.semilogx(xs_, VC['train_rmse'], '-o', label='train RMSE'); ax.semilogx(xs_, VC['val_rmse'], '-o', label='validation RMSE')
ax.set(title='Figure 4.1b  Validation curve: RMSE vs L2 lambda (0 plotted at 1e-5)', xlabel='lambda', ylabel='RMSE'); ax.legend()
plt.tight_layout(); plt.show(); VC
"""),
md(r"""
## 4.2 Dropout: rates and positions
**Rates** (one factor): 0, 0.1, 0.3 and 0.5 after every hidden layer. **Positions** (one factor, rate fixed at 0.3): early half only, late half only, and all hidden layers. A further run uses 0.1 dropout on the **inputs only**, which acts as feature noise.
"""),
code(r"""
DR = [run_reg(f'rate {p} (all hidden)', model_kw=dict(dropout=p)) for p in [0.0, 0.1, 0.3, 0.5]]
DP = [run_reg('early half (0.3)', model_kw=dict(dropout=0.3, dropout_positions='early')),
      run_reg('late half (0.3)', model_kw=dict(dropout=0.3, dropout_positions='late')),
      run_reg('inputs only (0.1)', model_kw=dict(input_dropout=0.1))]
DROP_SUM = reg_table(DR + DP); display(DROP_SUM)
fig, ax = plt.subplots(1, 2, figsize=(15, 3.8))
rates = [0.0, 0.1, 0.3, 0.5]; t = reg_table(DR)
ax[0].plot(rates, t['train_rmse'], '-o', label='train'); ax[0].plot(rates, t['val_rmse'], '-o', label='validation')
ax[0].set(title='RMSE vs dropout rate', xlabel='dropout rate', ylabel='RMSE'); ax[0].legend()
pos = DROP_SUM.loc[['rate 0.0 (all hidden)', 'early half (0.3)', 'late half (0.3)', 'rate 0.3 (all hidden)', 'inputs only (0.1)']]
ax[1].barh(pos.index, pos['gap(val-train RMSE)'], color=PAL[1]); ax[1].set(title='Generalisation gap (val - train RMSE) by position')
plt.suptitle('Figure 4.2  Dropout rates and positions', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
## 4.3 Early-stopping strategies
**One factor:** the stopping rule. Fixed: the over-parameterised network with a 200-epoch budget. Compared: no stopping; `val_loss` with patience 5 or 20; patience 20 **without** restoring the best weights; monitoring `val_mae` instead of `val_loss`; and a `min_delta` threshold.
"""),
code(r"""
ES = {'none (200 epochs)': dict(early_stop=False),
      'val_loss, patience 5': dict(early_stop=True, patience=5),
      'val_loss, patience 20': dict(early_stop=True, patience=20),
      'val_loss, patience 20, NO restore': dict(early_stop=True, patience=20, restore=False),
      'val_mae, patience 20': dict(early_stop=True, patience=20, monitor='val_mae'),
      'val_loss, min_delta 1e-3, patience 10': dict(callbacks_fn=lambda: [keras.callbacks.EarlyStopping(
            'val_loss', min_delta=1e-3, patience=10, restore_best_weights=True)])}
ES_RES = [run_reg(n, epochs=E(200), **kw) for n, kw in ES.items()]
ES_SUM = summarise(ES_RES); display(ES_SUM[['val_rmse', 'val_r2', 'val_qwk', 'train_rmse', 'gap(val-train RMSE)', 'best_epoch', 'epochs_run', 'time']])
full = ES_RES[0]['runs'][0]['hist']['val_rmse']
fig, ax = plt.subplots(figsize=(12, 4)); ax.plot(full.values, c='grey', label='validation RMSE (no stopping)')
for k, r in enumerate(ES_RES[1:], 1):
    e = r['runs'][0]['epochs_run']; ax.axvline(e, color=PAL[k], ls='--', label=f"{r['name']}: stops @ {e}")
ax.axvline(int(full.idxmin()) + 1, c='k', lw=2, label=f'minimum val RMSE @ {int(full.idxmin()) + 1}')
ax.set(title='Figure 4.3  Where each early-stopping rule halts training', xlabel='epoch', ylabel='val RMSE', ylim=(0.5, 1.0)); ax.legend(fontsize=8)
plt.tight_layout(); plt.show()
"""),
md(r"""
## 4.4 Bias–variance trade-off: capacity sweep
**One factor:** width (2 hidden layers of 2 to 512 units), with no regularisation and a fixed 100 epochs. Bias falls as capacity grows; variance (the train–validation gap) rises.
"""),
code(r"""
WIDTHS = [2, 8, 32, 128, 512]
CAP = reg_table([run_reg(f'width {w}', model_kw=dict(depth=2, units=w)) for w in WIDTHS])
params = [build_deep_model(N_FEAT, 2, w).count_params() for w in WIDTHS]
fig, ax = plt.subplots(figsize=(8, 3.8))
ax.semilogx(params, CAP['train_rmse'], '-o', label='train RMSE (bias proxy)'); ax.semilogx(params, CAP['val_rmse'], '-o', label='validation RMSE')
ax.fill_between(params, CAP['train_rmse'], CAP['val_rmse'], alpha=.12, color=PAL[3], label='gap (variance proxy)')
ax.set(title='Figure 4.4  Bias-variance: error vs model capacity', xlabel='# parameters', ylabel='RMSE'); ax.legend()
plt.tight_layout(); plt.show(); CAP.assign(params=params)
"""),
md(r"""
## 4.5 Learning curves vs training-set size
Three models are trained on 25%, 50%, 75% and 100% of the training set (stratified subsamples) and always scored on the full validation set:
- **High bias:** 1 hidden layer of 4 units with strong L2.
- **High variance:** 4 × 128 with no regularisation and no early stopping.
- **Tuned + early stopping:** the Section 3.6 configuration, regularised by early stopping (restoring the best weights).
"""),
code(r"""
FRACS = [0.25, 0.5, 0.75, 1.0]
LC_MODELS = {'High bias (1x4, L2=0.1)': dict(model_kw=dict(depth=1, units=4, reg=('l2', 0.1))),
             'High variance (4x128, no reg)': dict(),
             'Tuned + early stopping': dict(model_kw=TUNED, opt_fn=TUNED_OPT, callbacks_fn=PLATEAU, early_stop=True, patience=20)}
lc = []
for name, kw in LC_MODELS.items():
    for f in FRACS:
        sub = np.arange(len(X_train)) if f == 1 else train_test_split(np.arange(len(X_train)), train_size=f,
                                                                       stratify=y_train, random_state=SEED)[0]
        r = run_reg(f'{name}@{f}', X_tr=X_train[sub], y_tr=y_train[sub], **dict(kw))['runs'][0]
        lc.append(dict(model=name, n=len(sub), train_rmse=r['train_rmse'], val_rmse=r['val_rmse']))
LC = pd.DataFrame(lc)
fig, axes = plt.subplots(1, 3, figsize=(19, 3.9), sharey=True)
for ax, (n, g) in zip(axes, LC.groupby('model', sort=False)):
    ax.plot(g.n, g.train_rmse, '-o', label='train'); ax.plot(g.n, g.val_rmse, '-o', label='validation')
    ax.set(title=n, xlabel='# training samples', ylim=(0, 1.0))
axes[0].set_ylabel('RMSE'); axes[0].legend()
plt.suptitle('Figure 4.5  Learning curves vs training-set size', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
LC.pivot(index='n', columns='model', values=['train_rmse', 'val_rmse']).round(3)
"""),
md(r"""
<!--INTERP_PART4-->

## 4.6 Final model: selection by 5-fold cross-validation, then a one-time test evaluation
**Why cross-validation here.** Parts 3–4 select configurations on a *single* 204-row validation split. The seed-to-seed standard deviations (about 0.005–0.02 RMSE) are as large as many of the differences between configurations, so a single split can favour a configuration that merely fits that split well. The finalists are therefore compared with **stratified 5-fold cross-validation on train + validation** (1,155 wines). The preprocessing is re-fit inside every fold, and an inner 15% hold-out drives early stopping. The candidate with the lowest mean CV RMSE becomes the final model, which is trained on the training split (early stopping on validation) and scored **once** on the untouched test split, alongside the classical baselines.

| Candidate | Origin of the idea |
|---|---|
| Baseline | ReLU + He, Adam, ES (the Part 3 baseline) |
| Tuned (val-split winner) | Section 3.6: Swish + He + LayerNorm, SGD-Nesterov + ReduceLROnPlateau, ES |
| Tuned + light regularisation | adds Section 4.2's best dropout (0.1) and L2 = 1e-3 |
| Wide + regularised | Part 4's lesson: plenty of capacity (4 × 128) controlled by dropout 0.3 + L2 1e-3 + ES; <<WIDE_ACT_NAME>> activation, Adam |
"""),
code(r"""
df_trva = pd.concat([df_tr, df_va]); y_trva = df_trva['quality'].values.astype('float32')
FOLDS = list(StratifiedKFold(5, shuffle=True, random_state=SEED).split(df_trva, df_trva['quality']))

def cv_evaluate(model_kw, opt_fn, callbacks_fn=None, patience=20):
    rows = []
    for fold, (a, b) in enumerate(FOLDS, 1):
        p_f = make_preprocessor().fit(df_trva.iloc[a])                      # re-fit preprocessing inside the fold
        Xa, Xb = (pd.DataFrame(p_f.transform(df_trva.iloc[i]), columns=ALL_FEATS)[SELECTED].values.astype('float32') for i in (a, b))
        ia, ib = train_test_split(np.arange(len(a)), test_size=0.15, stratify=y_trva[a], random_state=SEED)   # inner ES split
        keras.utils.set_random_seed(SEED + fold)
        m = build_deep_model(N_FEAT, **model_kw); m.compile(optimizer=opt_fn(), loss='mse', steps_per_execution=16)
        m.fit(make_ds(Xa[ia], y_trva[a][ia]), validation_data=make_ds(Xa[ib], y_trva[a][ib], train=False), epochs=E(150), verbose=0,
              callbacks=[keras.callbacks.EarlyStopping('val_loss', patience=patience, restore_best_weights=True),
                         *(callbacks_fn() if callbacks_fn else [])])
        rows.append({'fold': fold, **reg_metrics(y_trva[b], predict(m, Xb))})
    return pd.DataFrame(rows).set_index('fold')

ADAM = lambda: keras.optimizers.Adam(1e-3)
CANDIDATES = {
    'Baseline (ReLU+He, Adam)': (BASE, ADAM, None, 15),
    'Tuned (val-split winner)': (TUNED, TUNED_OPT, PLATEAU, 20),
    'Tuned + dropout 0.1 + L2 1e-3': (dict(TUNED, dropout=0.1, reg=('l2', 1e-3)), TUNED_OPT, PLATEAU, 20),
    'Wide + regularised (4x128 <<WIDE_ACT_NAME>>, dropout 0.3, L2 1e-3, Adam)': (dict(depth=4, units=128, activation='<<WIDE_ACT>>', init='he_normal',
                                                                       dropout=0.3, reg=('l2', 1e-3)), ADAM, None, 25)}
CV_RES = {n: cv_evaluate(kw, o, cb, p) for n, (kw, o, cb, p) in CANDIDATES.items()}
CV_TABLE = pd.DataFrame({n: {**{f'cv_{c}_mean': d[c].mean() for c in ['rmse', 'mae', 'r2', 'qwk', 'good_auc']}, 'cv_rmse_std': d['rmse'].std()}
                         for n, d in CV_RES.items()}).T.sort_values('cv_rmse_mean')
display(CV_TABLE)
fig, ax = plt.subplots(figsize=(10, 3.2))
ax.barh(CV_TABLE.index[::-1], CV_TABLE['cv_rmse_mean'][::-1], xerr=CV_TABLE['cv_rmse_std'][::-1], color=PAL[0], capsize=3)
ax.set(title='Figure 4.6a  Final-candidate comparison: 5-fold CV RMSE (mean ± std across folds)', xlabel='CV RMSE',
       xlim=(CV_TABLE['cv_rmse_mean'].min() - .05, CV_TABLE['cv_rmse_mean'].max() + .05))
plt.tight_layout(); plt.show()

BEST = CV_TABLE.index[0]; FINAL_KW, FINAL_OPT, FINAL_CB, FINAL_PAT = CANDIDATES[BEST]
print('Selected by cross-validation:', BEST)
fin_runs = run_config('FINAL', FINAL_KW, FINAL_OPT, callbacks_fn=FINAL_CB, patience=FINAL_PAT)['runs']
final = min(fin_runs, key=lambda r: r['val_rmse'])['model']                 # seed chosen on VALIDATION only
p_test = predict(final, X_test)
rows = {f'Neural network (final: {BEST})': reg_metrics(y_test, p_test), 'Predict train mean': reg_metrics(y_test, np.full_like(y_test, Y_MEAN))}
for n, m in [('Ridge regression', Ridge(1.0)), ('Random forest', RandomForestRegressor(500, min_samples_leaf=2, random_state=SEED, n_jobs=-1))]:
    rows[n] = reg_metrics(y_test, m.fit(X_train, y_train).predict(X_test))
TEST_TABLE = pd.DataFrame(rows).T; TEST_TABLE
"""),
code(r"""
r_test = np.clip(np.rint(p_test), 3, 8).astype(int); yt = y_test.astype(int)
fig, ax = plt.subplots(1, 4, figsize=(23, 4.4))
sns.boxplot(x=yt, y=p_test, ax=ax[0], color=PAL[0]); ax[0].plot(range(len(np.unique(yt))), np.unique(yt), 'r--o', label='perfect')
ax[0].set(title='Predicted score by true score', xlabel='true quality', ylabel='predicted'); ax[0].legend()
labels = sorted(set(yt) | set(r_test)); cm = confusion_matrix(yt, r_test, labels=labels)
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False, ax=ax[1], xticklabels=labels, yticklabels=labels)
ax[1].set(title='Confusion matrix (rounded predictions)', xlabel='predicted', ylabel='true')
ax[2].hist(p_test - y_test, bins=30, color=PAL[2]); ax[2].axvline(0, c='k'); ax[2].set(title='Residuals (pred - true)')
fpr, tpr, _ = roc_curve(yt >= 7, p_test); ax[3].plot(fpr, tpr, label=f"AUC = {roc_auc_score(yt >= 7, p_test):.3f}")
ax[3].plot([0, 1], [0, 1], ':', c='grey'); ax[3].set(title='Flagging "good" wines (>=7) by predicted score', xlabel='FPR', ylabel='TPR'); ax[3].legend()
plt.suptitle('Figure 4.6b  Final model on the held-out test set', fontsize=14, weight='bold'); plt.tight_layout(); plt.show()
"""),
md(r"""
<!--INTERP_FINAL-->
"""),
md(r"""
## 4.7 Subgroup and error analysis (evidence for the fairness discussion in Part 5)
Errors are broken down by **true quality** and by **alcohol band**. A model trained with MSE on a score concentrated at 5–6 is expected to **regress toward the mean**: it over-scores poor wines and under-scores exceptional ones.
"""),
code(r"""
te = df_te.assign(pred=p_test, resid=p_test - y_test)
by_q = te.groupby('quality').agg(n=('pred', 'size'), mean_pred=('pred', 'mean'), mean_residual=('resid', 'mean'), mae=('resid', lambda r: r.abs().mean()))
by_band = te.groupby('alcohol_band').agg(n=('pred', 'size'), mean_true=('quality', 'mean'), mean_pred=('pred', 'mean'),
                                          mean_residual=('resid', 'mean'), mae=('resid', lambda r: r.abs().mean())).reindex(['low', 'medium', 'high'])
display(by_q.round(3)); display(by_band.round(3))
print(f'Total notebook runtime: {(time.time() - T_START) / 60:.1f} min')
"""),
md(r"""
<!--INTERP_SUBGROUP-->
"""),
]

# =============================================================================
# Part 5 + references
# =============================================================================
P5 = [md(r"""
<!--INTERP_PART5-->
"""), md(r"""
---
### References
- Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). Modeling wine preferences by data mining from physicochemical properties. *Decision Support Systems, 47*(4), 547–553.
- Glorot, X., & Bengio, Y. (2010). Understanding the difficulty of training deep feedforward neural networks. *AISTATS*.
- He, K., Zhang, X., Ren, S., & Sun, J. (2015). Delving deep into rectifiers. *ICCV*.
- Ioffe, S., & Szegedy, C. (2015). Batch normalization. *ICML*. · Ba, J. L., Kiros, J. R., & Hinton, G. E. (2016). Layer normalization. *arXiv:1607.06450*.
- Kingma, D. P., & Ba, J. (2015). Adam. *ICLR*. · Duchi, J., Hazan, E., & Singer, Y. (2011). AdaGrad. *JMLR*.
- Srivastava, N., et al. (2014). Dropout. *JMLR, 15*. · Ramachandran, P., Zoph, B., & Le, Q. (2017). Swish. *arXiv:1710.05941*.
- Loshchilov, I., & Hutter, F. (2017). SGDR: cosine schedules. *ICLR*. · Pascanu, R., Mikolov, T., & Bengio, Y. (2013). Gradient clipping. *ICML*.
""")]


def build(wide):
    tpl = nbf.read(TEMPLATE, as_version=4)
    t = tpl.cells
    assert len(t) == 18, len(t)
    fill = lambda cell, src: (setattr(cell, 'source', src.strip('\n')) or cell)

    cells = [t[0], t[1], *HEADER,
             fill(copy.deepcopy(t[2]), SETUP),
             t[3], t[4], fill(copy.deepcopy(t[5]), P1_FILL), *P1,
             t[6], t[7], fill(copy.deepcopy(t[8]), P2_FILL), *P2,
             t[9], t[10], fill(copy.deepcopy(t[11]), P3_FILL), *P3,
             t[12], t[13], fill(copy.deepcopy(t[14]), P4_FILL), *P4,
             t[15], t[16], fill(copy.deepcopy(t[17]), P5[0].source), P5[1]]
    for c in cells:
        if c.cell_type == 'code':
            c.outputs, c.execution_count = [], None
        c.source = c.source.replace('<<WIDE_ACT_NAME>>', wide[1]).replace('<<WIDE_ACT>>', wide[0])
    nb = nbf.v4.new_notebook(cells=cells, metadata={
        'colab': {'provenance': []},
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python'}})
    return nb


if __name__ == '__main__':
    nb = build(WIDE)
    nbf.write(nb, OUT)
    print('wrote', OUT.name, len(nb.cells), 'cells')
