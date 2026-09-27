# Predicting Amazon electronics prices from the listing

Given only a listing's description (title, category, brand, reviews, rating,
sales bin), how well can we predict its price, and how honest is the model
about its uncertainty? Data: 7,946 electronics products (493 brands, 22
categories) from a 10-day Amazon search scrape.

## Results

| | XGBoost | Bayesian hierarchical |
|---|---|---|
| new listing, known brand: within 2x of true price | **82%** | 80% |
| unseen brand: within 2x | 59% | **66%** |
| 80% intervals actually contain the price | 81% / 82% (after conformal calibration) | 81% / 80% |
| 80% interval width, unseen brand | x10.3 | **x6.7** |

- XGBoost gives the best single guess for known brands. The Bayesian model does better on unseen brands and gives tighter honest ranges (a $100 guess means "likely $70-144").
- After the title, brand moves price about ±55%, twice as much as category (±27%). High-volume brands are the cheaper ones (brand-level r = −0.56).

## Contents

- `src/1_data_cleaning` → `2_category_check` → `3_eda` → `4_price_model`: the notebooks, in order.
- [`METHODOLOGY.md`](METHODOLOGY.md): the decisions behind each step.
- `data/` holds the raw and cleaned CSVs; `labeling/` holds the category guidelines and hand labels; `archive/notebooks_full/` holds the original long notebooks.

## Reproduce

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd src && for n in 1_data_cleaning 2_category_check 3_eda 4_price_model; do
  ../.venv/bin/jupyter nbconvert --to notebook --execute --inplace $n.ipynb; done
```

The full run takes ~8 minutes on an M4.

Caveat: Kaggle calls the data synthetic, so results describe this dataset.
