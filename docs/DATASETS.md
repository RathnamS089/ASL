# Datasets: what to train or fine-tune on

Owners: Recognition (sign video) and Language/inference (gloss → text). Status: **shortlist for decision D1. Nothing has been downloaded.** Licences change, so read each dataset's current terms before downloading, and record what you agreed to in this file.

## Which model actually needs training?

| Model | Needs training? | On what |
| --- | --- | --- |
| **Sign recognizer** (video → glosses) | **Yes.** This is the main training effort of the project. | An isolated-sign video dataset in the chosen sign language (below), plus a few clips recorded by the team on the phones for testing. |
| **Text generator** (glosses → English) | **Probably not at first.** A pretrained small model with few-shot prompting and the code constraint may be enough (see [ml-service/MODEL_SELECTION.md](../ml-service/MODEL_SELECTION.md)). | Only if benchmarks show it is needed: a gloss–sentence parallel corpus (below). |

The sign language comes first (D1). Every dataset below covers exactly one sign language, so there is no single dataset that suits every language.

## Sign recognition (video → gloss)

Recommended MVP approach: **isolated sign recognition on pose and hand landmarks**. Extract landmarks per frame with a landmark model, then classify the sequence with a small temporal model (GRU, TCN or a small Transformer). Landmark sequences are small, train fast on a laptop, and are less sensitive to background and skin tone than raw pixels. These claims still need checking on our own data.

| Dataset | Language | Type | Size (per source) | Licence (as far as we know) | Fit |
| --- | --- | --- | --- | --- | --- |
| **ASL Citizen** (Microsoft Research) | ASL | Isolated, webcam recordings by Deaf/fluent signers | 83,399 videos, 2,731 signs, 52 signers ([paper](https://arxiv.org/abs/2304.05934v2)) | **Non-commercial research only**, under the Microsoft Research licence ([licence page](https://www.microsoft.com/en-us/research/project/asl-citizen/dataset-license/)) | **Best fit for ASL.** Webcam footage looks like our phone and laptop input, the signers were recorded with consent, and it has official splits by signer. |
| WLASL | ASL | Isolated, gathered from web videos | ~2,000 glosses | Research use. Videos come from third-party sites and many links are dead. **Verify the terms.** | Widely used for comparison, but noisier |
| MS-ASL | ASL | Isolated, from YouTube | ~1,000 signs | Research. YouTube availability varies. **Verify.** | Older. Use as a fallback. |
| How2Sign | ASL | **Continuous** sentences with English transcripts and some glosses | 80+ hours ([paper](https://arxiv.org/pdf/2008.08143)) | See the [download page](https://how2sign.github.io/#download). **Verify.** | Later, for continuous signing (after the MVP) |
| INCLUDE | Indian SL | Isolated | ~263 word signs (per paper) | **Verify** | The starting point if D1 = Indian SL |
| RWTH-PHOENIX-Weather 2014T | German SL | Continuous, weather broadcasts, glosses plus German text | — | Research. **Verify.** | Only if D1 = German SL. It is the standard benchmark for gloss→text. |

**How to choose for the MVP.**
1. Pick 20–50 everyday signs that appear in the chosen dataset, such as greetings, yes/no, help, thank you and family words.
2. Train on the dataset's own signers.
3. Report accuracy on a held-out set **split by signer**: signers in the test set never appear in training.
4. Separately, test on clips the team records on the phones. That second number is the honest one for the demo.

**Ethics and quality.**
- Involve fluent or Deaf signers to check the vocabulary and the outputs.
- Report results per signer and for left-handed signers.
- Do not publish team members' clips without consent.

## Gloss → text for the generator

| Corpus | Language pair | Notes |
| --- | --- | --- |
| ASLG-PC12 | ASL gloss ↔ English | Large, but the gloss side is **rule-generated from English**, not real ASL. Its licence is listed as unknown ([TFDS catalogue](https://tensorflow.org/datasets/community_catalog/huggingface/aslg_pc12)). Use it for experiments only, after checking terms. |
| How2Sign glosses + transcripts | ASL ↔ English | Real signing, but glosses cover only part of it. The authors note that glosses are an approximation, not a translation. |
| PHOENIX-2014T | German SL gloss ↔ German | Real broadcast data. Only relevant if D1 = German SL and the output is German. |
| **Team-written corpus (recommended if fine-tuning is needed)** | chosen language ↔ English | Write 300–1,000 gloss→sentence pairs using **only the recognizer's vocabulary**, reviewed by a fluent signer. A LoRA fine-tune of the chosen 2–4B model is then cheap. Check `benchmarks/glosses.jsonl` and keep it out of the training data so it stays a test set. |

## Decision checklist for D1

- [ ] Sign language chosen, with at least one isolated-sign dataset whose licence allows our use (academic and non-commercial is fine for the MVP; anything public needs review).
- [ ] At least one fluent signer is available to review vocabulary and test outputs.
- [ ] MVP vocabulary list (20–50 glosses) committed as `ml-service/vocabulary/<lang>.txt`.
- [ ] Download instructions written here (manual, not scripted, never committed to git).
