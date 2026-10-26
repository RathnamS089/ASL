# Training the sign recognizer on Google ISLR

> **Optional.** The app uses the pretrained 1st-place ISLR model by default (`models/recognizer/islr-1st-place`, see docs/ARCHITECTURE.md). Train our own only to change the vocabulary or architecture. Both share the same landmarks, segmenter and recognizer.

Data: [Google — Isolated Sign Language Recognition](https://www.kaggle.com/competitions/asl-signs) (Kaggle `asl-signs`). It has 250 ASL signs recorded on phones by Deaf signers, with MediaPipe Holistic landmarks already extracted. The licence is CC-BY 4.0 per the competition page; keep the attribution if you publish a model.

## 1. Get the data (your Kaggle account)

1. Sign in at kaggle.com, open the competition and **accept its rules**.
2. Go to Settings → API → *Create New Token*. Save the downloaded `kaggle.json` as `~/.kaggle/kaggle.json`, then make it private:

   ```bash
   chmod 600 ~/.kaggle/kaggle.json
   ```

3. Check the size before downloading. Your Mac needs room for the zip, the extracted files, and about 2.5 GB of prepared features:

   ```bash
   ml-service/.venv/bin/pip install kaggle
   ```

   ```bash
   ml-service/.venv/bin/kaggle competitions files asl-signs
   ```

4. Download and unzip into `ml-service/data/asl-signs/` (git-ignored):

   ```bash
   ml-service/.venv/bin/kaggle competitions download -c asl-signs -p ml-service/data
   ```

## 2. Prepare features and train (from `ml-service/`)

1. Prepare features. This uses the same feature code the server uses at runtime:

   ```bash
   .venv/bin/python training/islr/prepare.py --data data/asl-signs --out data/islr-features
   ```

2. Train on the M4 GPU with MLX. Validation and test signers are never trained on:

   ```bash
   .venv/bin/python training/islr/train.py --features data/islr-features --out models/recognizer/islr --epochs 40 2>&1 | tee models/recognizer/train.log
   ```

For a quick first run, add `--signs 50` to `prepare.py` to keep the 50 most frequent signs.

The result is written to `models/recognizer/islr/`:

| File | Contents |
| --- | --- |
| `weights.safetensors`, `config.json`, `labels.json` | The model |
| `metrics.json` | Test top-1/top-5 on held-out signers, plus per-epoch history |
| `VERSION` | Model version string |

`bin/run.sh` loads the model automatically when these files exist.

## What the numbers mean

- **`test_top1`** is accuracy on ISLR signers the model never saw, for isolated, pre-cut signs.
- **Real use is harder:** phone clips are cut automatically by the segmenter, and lighting and framing vary. Measure on your own recorded clips before quoting accuracy.
- **Vocabulary:** ISLR's 250 words are mostly everyday vocabulary from the PopSign app, like `TV`, `after` and `airplane`. They don't cover the phrases in `finetune/pairs.tsv`.
