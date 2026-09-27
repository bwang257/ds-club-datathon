"""Screen larger title-embedding models for the price model (XGBoost only, no PyMC).

Reproduces the 4_price_model.ipynb setup -- target log(current_price), inputs = 64 PCs of
the title embedding + text score (nested out-of-fold ridge on TF-IDF + embedding +
category) + log reviews, rating, log sales + category + brand -- and swaps the
embedding model. Family and brand grouped 5-fold CV, same seeds as the notebook.

    cd src && python embedding_screen.py all-MiniLM-L6-v2 BAAI/bge-base-en-v1.5 ...
    python embedding_screen.py --smoke all-MiniLM-L6-v2      # quick plumbing check

Writes ../data/embedding_screen.csv (appends one row per model x split).
Baseline to beat (MiniLM, notebook, 2026-09-25): XGBoost family R² 0.820 / within x2
80.7%; brand R² 0.593 / 57.5%.
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import xgboost as xgb
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

DATA = Path(__file__).resolve().parent.parent / 'data'
# e5 models expect a "query: " prefix; bge/gte/MiniLM take raw text
PREFIX = {'intfloat/e5-base-v2': 'query: ', 'intfloat/e5-large-v2': 'query: '}
XGB = dict(n_estimators=800, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.5,
           min_child_weight=3, enable_categorical=True, tree_method='hist', max_cat_to_onehot=1, random_state=0)
BANDS = [0, 25, 100, 500, np.inf]


def metrics(y, p):
    e = y - p
    band = lambda v: pd.cut(np.exp(v), BANDS, labels=False)
    return {'R2': 1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum(), 'x_error': np.exp(np.median(np.abs(e))),
            'within_x2': (np.abs(e) <= np.log(2)).mean(), 'band_acc': (band(y) == band(p)).mean()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('models', nargs='+')
    ap.add_argument('--smoke', action='store_true', help='800 rows, 50 trees: plumbing check only')
    args = ap.parse_args()

    d = pd.read_csv(DATA / 'amazon_products_deduped.csv')
    d = d[d['current_price'].notna()].reset_index(drop=True)
    if args.smoke:
        d = d.sample(800, random_state=0).reset_index(drop=True)
        XGB['n_estimators'] = 50
    y = np.log(d['current_price'].to_numpy())
    num = np.column_stack([np.log1p(d['number_of_reviews'].fillna(0)), d['rating'].fillna(d['rating'].median()),
                           np.log1p(d['bought_in_last_month'].fillna(0))]).astype(float)
    tfidf = TfidfVectorizer(token_pattern=r'[a-z0-9]+', ngram_range=(1, 2), min_df=2,
                            sublinear_tf=True).fit_transform(d['Title'].str.lower())
    cat = sp.csr_matrix(pd.get_dummies(d['category']).to_numpy(float))
    split_col = {'family': 'product_family', 'brand': 'brand'}
    splits = {k: list(GroupKFold(5, shuffle=True, random_state=0).split(d, groups=d[c])) for k, c in split_col.items()}

    for name in args.models:
        t0 = time.time()
        model = SentenceTransformer(name).float()  # gte loads as float16, which is very slow on CPU
        E = model.encode([PREFIX.get(name, '') + t for t in d['Title']], batch_size=64,
                         normalize_embeddings=True, show_progress_bar=False).astype(np.float32)  # gte ships float16
        t_embed = time.time() - t0
        Z = PCA(min(64, E.shape[1]), random_state=0).fit_transform(E)
        W = sp.hstack([tfidf, sp.csr_matrix(E), cat]).tocsr()
        for split, folds in splits.items():
            col = split_col[split]
            p_xgb, p_text = np.zeros(len(d)), np.zeros(len(d))
            for tr, te in folds:
                ts = np.zeros(len(d))  # text score: out-of-fold for train rows, full-train ridge for test rows
                for itr, ite in GroupKFold(5, shuffle=True, random_state=1).split(tr, groups=d[col].iloc[tr]):
                    ts[tr[ite]] = Ridge(1.0).fit(W[tr[itr]], y[tr[itr]]).predict(W[tr[ite]])
                ts[te] = Ridge(1.0).fit(W[tr], y[tr]).predict(W[te])
                p_text[te] = ts[te]
                T = pd.DataFrame(np.column_stack([Z, num, ts]))
                T.columns = [f'f{i}' for i in range(T.shape[1])]
                T['category'] = d['category'].astype('category')
                seen = sorted(set(d['brand'].iloc[tr]))
                T['brand'] = pd.Categorical(d['brand'].where(d['brand'].isin(seen)), categories=seen)
                p_xgb[te] = xgb.XGBRegressor(**XGB).fit(T.iloc[tr], y[tr]).predict(T.iloc[te])
            for which, p in [('xgboost', p_xgb), ('text score alone', p_text)]:
                row = {'model': name, 'dims': E.shape[1], 'split': split, 'predictor': which,
                       **{k: round(float(v), 4) for k, v in metrics(y, p).items()},
                       'embed_seconds': round(t_embed, 1), 'device': str(model.device), 'smoke': args.smoke}
                print(row, flush=True)
                out = DATA / ('embedding_screen_smoke.csv' if args.smoke else 'embedding_screen.csv')
                pd.DataFrame([row]).to_csv(out, mode='a', header=not out.exists(), index=False)


if __name__ == '__main__':
    main()
