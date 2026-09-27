# Methodology


## Data

Data was a scrape of Amazon search results: 42.7k rows collected on 6 days between Aug 21 and Aug 30, 2025, around the Labor Day sale. About 90% of the distinct products were electronics.

Raw columns (16), all stored as text:

| column | example | used? |
|---|---|---|
| `Title` | "BOYA BOYALINK 2 Wireless Lavalier Microphone for iPhone…" | yes: product ID, brand, category, embeddings |
| `Rating` | "4.6 out of 5 stars" | yes → number |
| `Number_of_reviews` | "2,457" | yes → number |
| `bought_in_last_month` | "300+ bought in past month" | yes → bin lower bound |
| `Current/discounted_price` | "89.68" (28% missing) | yes: shelf price, the model target |
| `Listed_price` | "$159.00" or "No Discount" | no |
| `Price_on_variant` | "basic variant price: $162.24" | no (a different variant's price) |
| `is_best_seller` | "Best Seller", "Amazon's", "Limited time deal" | yes: Amazon's Choice flag |
| `is_sponsored` | "Sponsored" / "Organic" | yes |
| `is_couponed` | "Save 15% with coupon" / "No Coupon" | yes: has coupon |
| `buy_box_availability` | "Add to cart" or blank | yes: in stock |
| `delivery_details` | "Delivery Mon, Sep 1" | no |
| `sustainability_badges` | "Carbon impact", "Small Business" (92% blank) | no |
| `image_url` | product photo link | no (used only in the labelling tool) |
| `product_url` | product link (13% one-time ad tokens) | no |
| `collected_at` | "21-08-2025 11:14" | yes: dedup (latest scrape) and scrape-count checks |


## Cleaning (`1_data_cleaning`)
- 962 duplicate rows dropped.
- Converted rating, review count and price strings to numbers with regex ("4.6 out of 5 stars", "$1,299").
- Used the shelf price (`current_price`). Coupons are temporary, so they aren't part of the price.
- The `is_best_seller` field mixes Best Seller, Amazon's Choice and deal badges → pulled out the Amazon's Choice flag.
- Last-month sales are stored as the lower bound of the bin (300+ → 300). In-stock listings with no sales badge (<50) are coded as 0.
- Left other missing entries missing, and dropped columns the analysis doesn't use.
- Kept one row per product. The scraper recaptured some listings many times: the top 1% of products are 37% of rows.

- ~170 non-electronics (toys, kitchen, backpacks with no device) and 58 plain-stationery items → dropped, since the question is about electronics.


## Brands column
- Used trial-and-error regex to get brands. Judged each change by manual inspection in Excel, then manually inspected 150 titles to get a success rate of 98%.
	- strip trademark symbols, skip quantities and sizes
	- had Claude create a short list of multi-word brands. If the title starts with one, we use it
	- skip words that aren't names and move to the first real word
	- for generic words like "wireless" or model codes like "AX3000", look later in the title for a known brand (a word that starts 3 or more titles). Otherwise, we call it Unbranded.
	- merged sub-brands using a Claude-generated lookup table (e.g. Legion → Lenovo)

## Categories column
Similar to the brand column process: at first, manual inspection of the Excel sheet was used to judge success. This was a harder problem because some products had only minor hints about what they were.

Began with regex: generated patterns with Claude, such as any item with "headphone" being classified as Audio. Corrected mistakes over multiple rounds, such as only looking at the text before "for" first, or not letting feature words like "display" on a smartwatch mean Monitors.

Faced diminishing marginal returns, so we added a model on top: embed the product title with a publicly available pretrained embedding model, then put the regex output and the embedding into a logistic regression, so it learns when the regex pattern tends to be wrong and outputs fixes. Ran 5 different embedding models and compared results:

| embedding model | size | held-out hand labels (n=80) | random 250, hand labels | hard cases (n=972) | embed time |
|---|---|---|---|---|---|
| **all-MiniLM-L6-v2** | 22M | 93.8% | 95.1% | 76.2% | 6 s |
| bge-base-en-v1.5 | 110M | 96.2% | 95.1% | 76.7% | 25 s |
| e5-base-v2 | 110M | 95.0% | 94.7% | 72.4% | 27 s |
| gte-base | 110M | 95.0% | 95.1% | 73.3% | 22 s |
| bge-large-en-v1.5 | 335M | 95.0% | 95.1% | 76.0% | 87 s |

Selected all-MiniLM-L6-v2 because all five tie within noise: on the 80 held-out products, the gap between the best and worst is 2 products. MiniLM is the smallest and fastest. "Hard cases" are the ~970 products with a reference label, mostly ones the rules got wrong.

Validation: accuracy is measured against hand labels. I hand-labelled 250 random products, and there's a separate 160-product gold sample (80 used while writing rules, 80 held out). Due to time constraints, the harder cases (604 products the rules were most likely to get wrong) were labelled by Claude Sonnet agents instead of by hand. I sanity-checked those against the gold sample (96% agreement) and used them to train and correct the model, not to measure accuracy. The fully automatic label is right 93.8% of the time on the held-out sample.

## Exploration findings (`3_eda`)
- Median price varies 15x across categories ($15 for Batteries to $230 for Marine & GPS) → prices are compared within category.
- Cheap products have more reviews and sell more:

| vs monthly sales | Spearman | within category |
|---|---|---|
| reviews | +0.62 | +0.58 |
| price | −0.56 | −0.47 |
| rating | +0.22 | +0.16 |

  Price vs reviews: r = −0.47 (log-log).
- Protection plans were the largest single "brand" in the raw data (666 Asurion plans, 3,068 rows, ~7.6% of products). Dropped, because they are outside the primary set of electronic products. They are also an add-on, none of the 666 plans was in stock or had a sales count, and only 6 showed a price.

## Price model (`4_price_model`)

- Question I wanted to ask: predict the shelf price from the listing description (title, category, brand, reviews, rating, sales bin). My background interest was in probabilistic models. EDA revealed that some brands have only one product (28% of brands) while some have a lot (HP had 508). Groups are also related through competition, and prices depend on both brand and category. Partial pooling made a lot of sense, so I wanted to build around a Bayesian hierarchical model. The data was tabular, so I knew XGBoost was the industry standard, and I wanted to compare the two. Target: 80% of predictions within 2x of the true price.
- Prices run from $2.50 to $4,700 and errors are proportional → we model log price.
- Scrape time, sponsored, coupon and in-stock describe the moment, not the product, and hurt on new brands → excluded.
- The title is embedded the same way as for categories. Here, 5 embedding models were screened with XGBoost, and gte-base was chosen: the three base-size models tie, all beat MiniLM by ~1.5 points, and the large model adds <1 point for 3x the time.

| embedding model | known brand: within x2 | unseen brand: within x2 | embed time (CPU) |
|---|---|---|---|
| all-MiniLM-L6-v2 | 80.8% | 56.9% | 2 min |
| bge-base-en-v1.5 | 82.1% | 58.2% | 12 min |
| e5-base-v2 | 81.6% | 59.1% | 12 min |
| **gte-base** | 81.9% | 58.5% | 11 min |
| bge-large-en-v1.5 | 82.3% | 59.0% | 40 min |

I wanted the models to give an interval, so I used quantile regression on XGBoost to predict the 10th and 90th percentiles.

Initial analysis of the performance showed that the embedding misses model numbers, like RTX 5080 vs 3050:

| product | true price | first version | final model (XGBoost / Bayesian) |
|---|---|---|---|
| PNY RTX 5080 graphics card | $1,099 | $272 | $581 / $537 |
| Canon EOS R6 Mark II kit | $2,299 | $468 | $1,520 / $2,145 |
| Samsung Galaxy Tab S10+ | $881 | $260 | $222 / $213 |

Decided to run TF-IDF and then a ridge regression (L2, which shrinks large coefficients) on log price to get a text score, computed out-of-fold so a product's score never sees its own price. It was the biggest single gain: overall R² went from 0.78 to 0.82 for XGBoost and from 0.71 to 0.81 for the Bayesian model. It helped the camera a lot and the graphics card partly; the tablet is still far off.

Then I ran conformal calibration. The raw quantile intervals for XGBoost were too narrow: they held the true price only 62% of the time on known brands and 71% on unseen brands, instead of 80%. So we held out 20% of the training groups, measured how far their true prices fell outside the band, and widened every interval by that amount. That brought coverage to 81% on known brands and 82% on unseen ones, at the cost of wider intervals (x10.3 vs the Bayesian model's x6.7 on unseen brands).

| | XGBoost | Bayesian |
|---|---|---|
| known brand: within x2 of true price | **82%** | 80% |
| unseen brand: within x2 | 59% | **66%** |
| 80% interval coverage (known / unseen brand) | 81% / 82% (conformal) | 81% / 80% |
| 80% interval width, unseen brand | x10.3 | **x6.7** |

- **Takeaways:** XGBoost gives the best single guess for known brands. The Bayesian model does better on unseen brands and gives tighter ranges.
	- Also see:
		- Since the BHM prices a product in layers (start with the title, then adjust for category, then brand, etc.), we can read its parameters. Analysis of the Bayesian model's parameters reveals that, once we know what a product is from its title, the brand still shifts its price by about ±55%, twice as much as its category (±27%).
- High-volume brands are systematically the cheaper ones:

| brand's average (across its listings) | price effect per SD | 89% interval |
|---|---|---|
| **monthly sales** | **x0.90** | x0.84 to x0.97 |
| review count | x0.96 | x0.90 to x1.03 (no clear effect) |
| rating | x1.02 | x0.97 to x1.08 (no clear effect) |

  A brand whose products sell one standard deviation more than average prices ~10% lower (e.g. Amazon Basics, Anker, UGREEN). This is an association: cheap products also sell more.



Next steps:
- Categories: more hand labelling, especially where the logistic regression model is least sure. Build a bigger held-out test set. Deeper analysis of the confusions.
- Brands: the product page lists the brand but the scrape doesn't include it, so run my own scrape for it. Not done because the Kaggle dataset had a notice that the data might be synthetic.
