"""Markdown discussion injected into the executed notebook at the <!--INTERP_*--> markers.

Numbers quoted here come from the executed run (SEED=42, seeds [42, 7]); a re-run on other
hardware can shift values slightly, but the directions discussed are stable.
"""

INTERP = {}

INTERP['PART2'] = r"""
### 2.5 Findings: how gradients change with depth
**Regime A, sigmoid + Xavier (vanishing).**
- **Observation:** at initialisation the first-layer gradient falls from 3.4×10⁻² (3 layers) to 4.3×10⁻⁸ (12 layers), almost six orders of magnitude. Meanwhile the last hidden layer still receives gradients of order 1 (Figure 2.2a, left; Figure 2.3). The ratio between first and last layer falls by about 0.65–1.0 decades *per layer*. The 3-layer network learns (validation R² = 0.32), but the 6-, 9- and 12-layer networks never move off the mean prediction (R² ≈ −0.02; the validation RMSE stays flat at the predict-the-mean level in Figure 2.2c).
- **Reason:** backpropagation multiplies by σ′(z) ≤ 0.25 and by the weight matrix at every layer, so the signal shrinks geometrically with depth. The heatmap (Figure 2.2b) shows the gradients stay this way throughout training, because the early layers cannot learn their way out.
- **Impact:** in deep sigmoid networks the early layers stay effectively frozen at their random initial values. Adding depth then adds cost without adding capacity.

**Regime B, ReLU + He (healthy, but depth still costs stability).**
- **Observation:** the gradient profile is almost flat at every depth (a first/last ratio of 0.08–0.21, decaying only 0.10–0.34 decades per layer). The 3- and 6-layer networks train normally (R² = 0.28 and 0.35). However, the 9- and 12-layer networks **diverged to NaN in the first epoch**: the gradient norm at the output end grows with depth (29 → 52 for the last hidden layer, peaking around 60).
- **Reason:** He initialisation preserves the *variance* of the signal through ReLUs, which solves the vanishing problem. But it does not bound the *size* of a momentum-SGD step. With more layers there are more parameters whose updates add up through the multiplicative chain, so lr = 0.01 with momentum 0.9 becomes too large.
- **Impact:** good initialisation is necessary but not sufficient for deep networks. It should be combined with normalisation, gradient clipping, a smaller or adaptive learning rate, or residual connections.

**Regime C, ReLU + N(0, 0.5²) (exploding).**
- **Observation:** first-layer gradients at initialisation grow from 1.6×10² (3 layers) to 1.5×10⁴, 1.3×10⁷ and 5.2×10⁹ (12 layers), roughly ×10² for every three layers added. Every depth diverged to NaN within the first epoch.
- **Reason:** an initial standard deviation about 2.8× the He value multiplies the forward variance by about 8 per layer, and the backward pass inherits the same growth.

**Remedies (Figure 2.4).**
- *Gradient clipping* stopped the NaNs, so all 40 epochs completed, but the network stayed at R² = 0. Clipping caps the step size; it does not repair the badly scaled forward pass, so the units remain saturated.
- *BatchNorm* fixed the root cause. The maximum gradient norm fell from 7×10¹⁰ to 2.0 and validation R² reached 0.23.
- For the vanishing sigmoid network, BatchNorm lifted the first-layer gradient from about 10⁻⁸ to about 1, a flat profile. It reached a validation RMSE of about 0.64 mid-training, although without early stopping it was unstable by epoch 40. Section 3.4 confirms the rescue on a 9-layer network (R² 0.37 vs 0).

**Summary of how gradients change with depth:** with saturating activations the gradient magnitude falls **exponentially** with depth; with an over-scaled initialisation it **grows exponentially**; with ReLU + He it stays roughly **constant** in shape, but its absolute size, and therefore training stability, still grows with depth.
"""

INTERP['OPT'] = r"""
**Optimiser findings (Figures 3.1a–b).**
- **Observation:** at the default learning rates, **AdaGrad (0.6257 ± 0.002)** and **SGD + Nesterov momentum (0.6293 ± 0.016)** reach the lowest validation RMSE, ahead of Adam (0.6426) and RMSprop (0.6529). Adam and RMSprop reach their best epoch fastest (epochs 7–10) but also overfit fastest: their train–validation gap is 0.11–0.12 RMSE, against about 0.07 for AdaGrad and SGD + Nesterov. Plain SGD converges slowly (best epoch about 31).
- The learning-rate sweep changes the ranking. **Adam at lr = 0.01 (0.620)** and **AdaGrad at lr = 0.1 (0.623)** are the best cells overall, while Adam at 0.1 collapses to the mean (0.821) and SGD + Momentum at 0.1 diverges (blank cell).
- **Reason:** AdaGrad's accumulated squared gradients shrink its step size over time, a built-in decay that suits a small, quickly learned dataset. Adam's bias-corrected moments allow larger steps, which help at moderate learning rates but overshoot at 0.1.
- **Impact:** optimiser rankings depend on the learning rate. Each optimiser must be tuned before comparing them, and the differences at their best settings (about 0.005 RMSE) are smaller than the seed-to-seed spread.
"""

INTERP['INIT'] = r"""
**Initialisation findings (Figure 3.2).**
- **Observation:** all variance-scaled schemes cluster together (val RMSE 0.627–0.645): LeCun normal 0.6265, Xavier normal 0.6270, Xavier uniform 0.6305, He normal 0.6315, He uniform 0.6448. The naive schemes fail completely. **Zeros** and **small N(0, 0.01)** stay at the mean prediction (R² = 0; QWK = 0). **Large N(0, 1)** diverges to NaN in the first epoch.
- **Reason:** with zeros, every unit in a layer computes the same output and receives the same gradient, so this symmetry is never broken. With std 0.01 the forward signal shrinks by about 10× per layer (Figure 3.2, left), so both activations and gradients vanish. With std 1 the signal grows instead, causing explosion. The Glorot, He and LeCun formulas set Var(W) ∝ 1/fan so that activation variance stays roughly constant across layers (flat lines in the forward-signal panel).
- He normal had the **lowest variance across seeds** (std 0.004) and is the theoretically matched choice for the ReLU family, so it is kept for later experiments.
- **Impact:** at depth 6 the choice among principled initialisers matters far less than avoiding an unprincipled one. A bad initialisation is a failure mode, not a small accuracy cost.
"""

INTERP['ACT'] = r"""
**Activation findings (Figures 3.3a–b).**
- **Observation:** **tanh + Xavier (0.6284)** and **Swish (0.6348 ± 0.002)** lead, followed by Leaky ReLU (0.6458), ReLU (0.6468) and ELU (0.6995). Plain ReLU left **1.4%** of hidden units dead (they output zero for every training wine). Leaky ReLU cut this to 0.5%, and ELU, Swish and tanh had none. Swish also had the **smallest generalisation gap** (0.025), while ELU overfit most (gap 0.26, best epoch 16.5).
- **Reason:** Swish (x·σ(x)) is smooth and non-monotonic, and lets small negative values through, so gradients never become exactly zero and units cannot die. ReLU's zero gradient for negative inputs is what produces dead units. The smooth bounded activations (tanh, Swish) also act as a mild regulariser on this small, noisy target.
- **Impact:** Swish is the best of the four ReLU-family activations the rubric names. Its low seed variance makes it a dependable default, so it is carried into Section 3.6 and into the final-candidate pool.
"""

INTERP['NORM'] = r"""
**Normalisation findings (Figure 3.4).**
- **(a) Rescue setting.** The 9-layer sigmoid network without normalisation, and with LayerNorm, stays at the mean prediction (val RMSE 0.8208, R² ≈ 0). **BatchNorm rescues it: val RMSE 0.6495, R² 0.37.** Its gradient profile at initialisation becomes flat instead of falling by orders of magnitude.
- **(b) Modern setting.** With ReLU and Adam, **LayerNorm** gives the best and most stable result (0.6332 ± 0.004), while BatchNorm is *worse* than no normalisation (0.6746 ± 0.037, gap 0.137).
- **Reason:** BatchNorm re-centres each unit's pre-activation across the batch, which keeps sigmoid inputs in the region where σ′ is largest and so restores gradient flow. LayerNorm normalises across the units of one sample. For a sigmoid, that does not stop units from all saturating together, so it cannot fix vanishing. Once gradients are healthy, BatchNorm's batch-to-batch noise with batches of 64 (and the train/inference mismatch) adds variance, whereas LayerNorm behaves the same at training and inference time.
- **Impact:** use BatchNorm to make a deep, poorly conditioned network trainable. In small-batch tabular settings LayerNorm is the safer stabiliser. (Section 4.6 shows LayerNorm's single-split advantage does not hold up under cross-validation.)
"""

INTERP['SCHED'] = r"""
**Learning-rate schedule findings (Figure 3.5).**
- **Observation:** all schedules reach a similar *best* validation RMSE at some epoch (0.636–0.644), because the first few epochs are almost identical. They differ sharply in what happens **afterwards**. With a **constant** rate the network keeps fitting the training set (train RMSE 0.21) and validation RMSE drifts up to **0.754** (gap 0.54). **ReduceLROnPlateau** ends best (**0.656**, gap 0.20, perfectly stable final epochs), followed by exponential decay (0.666) and step decay (0.693). Cosine with warm-up ends at 0.723: it keeps the learning rate high for most of the run, so it overfits before it anneals.
- **Reason:** a decaying learning rate shrinks the step size once the loss surface has been explored, so the optimiser settles rather than continuing to memorise noise. ReduceLROnPlateau does this adaptively, at the moment validation loss stops improving.
- **Impact:** for fixed-budget training, a feedback-driven schedule gives the best and most stable end-of-training model. It is also a safety net if early stopping is misconfigured.
"""

INTERP['COMBO'] = r"""
**Combined configuration (Figure 3.6).**
- **Observation:** combining the individually best choices (Swish + He + LayerNorm, SGD-Nesterov with ReduceLROnPlateau) improves on the baseline in validation: RMSE **0.6261 vs 0.6426**, R² 0.418 vs 0.387, QWK 0.574 vs 0.533, and a smaller train–validation gap (0.072 vs 0.110).
- **Caveat:** each component was chosen on the same 204-row validation split that this comparison uses. The improvement is about one seed-standard-deviation, so it could partly reflect that split rather than a real gain. Section 4.6 tests this with cross-validation before anything is used on the test set.
"""

INTERP['PART4'] = r"""
### 4.5b Findings: regularisation, bias and variance
**Weight penalties (Figure 4.1a).**
- **Observation:** the unregularised 4 × 128 network memorises the training set: train RMSE 0.12 against validation 0.70 at epoch 100, a gap of 0.58. Its validation error is lowest around epoch 5 (min 0.634) and then climbs. **L1** drives 20% of weights below 10⁻³ (sparsity, versus 0.6% without), **elastic net** 13%, and **L2** shrinks the overall weight norm from 33 to 21 with only 4% sparsity.
- At the strengths in this first comparison, the penalties reduce the gap only modestly. The **validation curve (Figure 4.1b)** shows why: the penalty must be strong enough to matter. At **λ = 0.01** the gap falls from 0.59 to 0.26, and the best validation RMSE improves to 0.612. At **λ = 0.1** the gap almost disappears (0.008), but training error rises to 0.67: underfitting, with high bias.
- **Reason:** L1's constant pull (sign(w)) zeroes out small weights; L2's proportional pull (2λw) shrinks all weights smoothly; elastic net combines the two.

**Dropout (Figure 4.2).**
- **Observation:** a rate of **0.1 is the best single regulariser on validation (RMSE 0.629, R² 0.41)**, while 0.3 and 0.5 underfit (train RMSE 0.65–0.74). Position matters at a fixed 0.3: dropout in the **early** half generalises better (0.644, gap 0.11) than in the **late** half (0.661, gap 0.44). Input-only dropout barely helps (gap 0.47).
- **Reason:** dropout in early layers forces redundant feature detectors at the representation stage, where co-adaptation is most harmful. Late dropout only perturbs a representation that has already been learned.

**Early stopping (Figure 4.3).**
- **Observation:** without stopping, 200 epochs end at val RMSE 0.711 (train 0.10). Every strategy that **restores the best weights** recovers the epoch-5 model (val RMSE **0.626**, gap 0.07) at a fraction of the cost: patience 5 stops at epoch 10, `min_delta` at 15, patience 20 at 25. Monitoring `val_mae` instead of `val_loss` makes no difference here. **Patience 20 without restoring** keeps the last, already overfitted weights (0.689).
- **Impact:** with restoration enabled, patience mainly trades compute for robustness against noisy validation curves. `restore_best_weights=True` is the setting that actually matters.

**Bias–variance (Figures 4.4–4.5).**
- **Observation:** the capacity sweep traces the classic U-shape. Width 2 underfits (train ≈ val ≈ 0.68: **high bias**). **Width 8 is the sweet spot** (val 0.624, gap 0.02). From width 32 upwards, training error keeps falling while validation error rises to 0.73 (gap up to 0.56: **high variance**).
- The learning curves agree. The high-bias model's training and validation errors converge around 0.65–0.66, and more data barely helps. The high-variance model keeps a training error near zero and a gap of 0.6–0.7 at every size. The tuned model with early stopping has the lowest validation error at full size (0.621), and its gap stays small.
- **Impact:** with about 1,000 rows, this problem is **variance-limited**. Capacity must be paired with strong regularisation (or kept small), and early stopping with weight restoration is the cheapest effective control.
"""

# Section 4.6/4.7 and Part 5 are filled in after the final run (see fill_final()).

INTERP['FINAL'] = r"""
**Final-model findings (Figures 4.6a–b).**
- **Observation, model selection:** cross-validation **reverses the single-split ranking**. The Section 3.6 "tuned" network won on the validation split (0.626), but under 5-fold CV it scores **0.680 ± 0.020**. The **wide, regularised Swish network** (4 × 128, dropout 0.3, L2 1e-3, Adam, early stopping) is clearly best at **0.639 ± 0.025** (R² 0.40), ahead of the tuned network with light regularisation (0.670) and the baseline (0.693). In exploratory ablations on two CV shuffles, removing dropout and L2 cost about 0.06 RMSE, and swapping Swish for ReLU about 0.025.
- **Observation, one-time test:** the selected network achieves **test RMSE 0.652, MAE 0.510, R² 0.374 and QWK 0.521**. **97.6% of predictions are within ±1 point**, and the predicted score flags "good" wines with **ROC-AUC 0.90**. This is level with the random forest (RMSE 0.650, R² 0.377), better than ridge regression (0.661), and far better than predicting the mean (0.824). The test result agrees with the CV estimate (0.639 ± 0.025), so the selection did not overfit.
- **Reason:** LayerNorm and SGD-Nesterov fitted the particular 204 validation wines well, but those choices did not transfer to other partitions. Generous capacity held in check by strong regularisation generalises better on noisy, ordinal sensory labels.
- **Impact:** on a dataset this small, configurations should be selected with cross-validation (or repeated splits) rather than one validation split. A well-regularised neural network matches, but does not beat, a tuned tree ensemble here, which is a fair result for 1,000 tabular rows.
"""

INTERP['SUBGROUP'] = r"""
**Error-analysis findings.**
- **Observation:** errors are strongly **regressed toward the mean**. Wines rated 3–4 are over-predicted by +1.2 to +2.3 points, while wines rated 7 are under-predicted by −0.73 and wines rated 8 by −1.68. By alcohol band, high-alcohol wines (≥ 11.5%) have the largest error (MAE 0.60 vs 0.44 for low-alcohol wines) and are systematically under-scored (mean residual −0.19).
- **Reason:** MSE training on a target where 82% of labels are 5 or 6 rewards hedging toward about 5.6. The extremes (3, 4, 8) make up about 6% of the training data, so the model sees too few examples to commit to them.
- **Impact:** the model is most reliable exactly where it is least needed (ordinary wines), and least reliable for the exceptional or flawed wines that matter most to buyers and producers. This motivates the fairness discussion in Part 5.
"""

INTERP['PART5'] = r"""
### Written Analysis & Reflection

**Optimisation experiments and gradient flow.** With sigmoid activations and Xavier initialisation, the first-layer gradient fell from 3×10⁻² at three layers to 4×10⁻⁸ at twelve, and every network deeper than three layers was stuck predicting the mean. ReLU with He initialisation kept the gradient profile almost flat. Even so, the 9- and 12-layer networks diverged under momentum SGD as gradient magnitude grew with depth. An over-scaled initialisation produced gradients up to 7×10¹⁰ and immediate divergence. BatchNorm fixed both pathologies at their source. Gradient clipping prevented NaNs, but a badly scaled network still could not learn.

**Comparison of techniques.** Once tuned, optimisers differed by only about 0.005 RMSE; the learning rate mattered more than the optimiser. Any variance-scaled initialiser worked, while zeros, tiny and large initialisations failed outright. Swish avoided dead units and had the smallest generalisation gap. LayerNorm suited small-batch training better than BatchNorm. ReduceLROnPlateau gave the most stable end-of-training model. The data's main constraint is **variance**: an unregularised network overfits within about five epochs. Early stopping with weight restoration, dropout around 0.1–0.3 in early layers, and L2 around 10⁻³–10⁻² were the most effective controls. Five-fold cross-validation showed that my validation-split "winner" did not generalise. The final regularised Swish network reached test RMSE 0.65, R² 0.37 and ±1 accuracy of 97.6%, on par with a random forest.

**Bias and fairness concern.** The model systematically **compresses scores toward the average**: wines rated 8 are under-predicted by about 1.7 points and wines rated 3 over-predicted by about 2.3. The labels are also the median of a few Portuguese *vinho verde* tasters, so they encode one regional panel's taste. If such a system were used to price, list or certify wines, distinctive producers whose wines fall outside that profile would be penalised. Alcohol, the dominant feature, could also become a proxy for "quality" that favours warmer-climate or riper styles.

**Optimisation choices and reliability.** Choices that look equivalent on one split can diverge in deployment. A learning rate slightly too high produced NaNs, BatchNorm's batch dependence created unstable predictions, and a single-split choice overfit the validation set. Fixed seeds, cross-validated evaluation and stable schedules reduce the risk that a retrained model behaves differently from the approved one.

**Production recommendations.** (1) Select models with cross-validation and report uncertainty, not single-split scores. (2) Monitor gradient norms and loss for NaNs during training, with clipping and early stopping as safeguards. (3) Prefer normalisation that does not depend on batch statistics for small-batch or online inference. (4) Version the preprocessing pipeline with the model, since the Yeo–Johnson parameters are fitted to training data. (5) Audit errors by quality band and style, and route extreme predictions to human experts. (6) Monitor for drift when chemistry or vintages differ from the training distribution, and benchmark against simple models before accepting a neural network's added complexity.
"""
