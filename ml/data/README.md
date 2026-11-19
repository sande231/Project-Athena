# Dataset (not committed to Git)

1. Sign in to Kaggle and accept the rules of the
   [IEEE-CIS Fraud Detection competition](https://www.kaggle.com/competitions/ieee-fraud-detection).
2. Download and unzip into this folder so you have:
   - `ml/data/train_transaction.csv`
   - `ml/data/train_identity.csv`

With the Kaggle CLI:

```bash
kaggle competitions download -c ieee-fraud-detection -p ml/data
unzip ml/data/ieee-fraud-detection.zip -d ml/data
```

The CSV files are large (about 1.3 GB) and are ignored by `.gitignore`. Do not commit them.
