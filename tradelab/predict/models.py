"""Model ladder: no-skill and simple-rule baselines, regularised linear/logistic, gradient-boosted trees.
Every fitted transform (scaling, imputation) is fit inside the training fold only."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class Spec:
    name: str
    kind: str                       # "zero" | "base_rate" | "rule" | "ridge" | "logit" | "gbt_reg" | "gbt_clf"
    target: str                     # label column
    features: list[str] = field(default_factory=list)
    rule: str | None = None         # for kind == "rule": column whose (signed) value is the score
    sign: float = 1.0
    params: dict = field(default_factory=dict)


def fit_predict(spec: Spec, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    y = train[spec.target].to_numpy(float)
    if spec.kind == "zero":
        return np.zeros(len(test))
    if spec.kind == "base_rate":
        return np.full(len(test), np.nanmean(y))
    if spec.kind == "rule":
        return spec.sign * test[spec.rule].to_numpy(float)
    X, Xt = train[spec.features], test[spec.features]
    if spec.kind == "ridge":
        m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=spec.params.get("alpha", 100.0)))
        return m.fit(X, y).predict(Xt)
    if spec.kind == "logit":
        m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(C=spec.params.get("C", 0.05), max_iter=2000))
        return m.fit(X, y.astype(int)).predict_proba(Xt)[:, 1]
    if spec.kind == "gbt_reg":
        m = HistGradientBoostingRegressor(max_depth=spec.params.get("max_depth", 3), learning_rate=0.05, max_iter=200,
                                          min_samples_leaf=spec.params.get("min_samples_leaf", 200), l2_regularization=1.0,
                                          random_state=0)
        return m.fit(X, y).predict(Xt)
    if spec.kind == "gbt_clf":
        m = HistGradientBoostingClassifier(max_depth=spec.params.get("max_depth", 3), learning_rate=0.05, max_iter=200,
                                           min_samples_leaf=spec.params.get("min_samples_leaf", 200), l2_regularization=1.0,
                                           random_state=0)
        return m.fit(X, y.astype(int)).predict_proba(Xt)[:, 1]
    raise ValueError(spec.kind)
