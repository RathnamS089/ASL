# Validation on real ASL videos

These are checks on real signers the models never trained on. The videos are YouTube lessons, downloaded only to this Mac (`data/youtube/`, git-ignored, never redistributed). Only the scores and the scripts are committed.

| Video | Used for |
| --- | --- |
| [ASL: Family](https://www.youtube.com/watch?v=N45u5W3rOBc) (Miacademy) | Whole signs: dad, mom, grandpa, grandma, brother, aunt, uncle, plus 7 signs outside the vocabulary |
| [Learn ASL ABCs with Memory Tips](https://www.youtube.com/watch?v=wvTrlW5z4SM) (Our Berg Life) | Letters A–Z, close-up of one hand |

Ground truth comes from each video's English captions: the time each sign or letter is taught. Frame grabs confirm that the on-screen labels line up.

## To reproduce

Run these from `ml-service/`.

1. Download the videos (480p, H.264) and their captions:

   ```bash
   yt-dlp -f 135 --write-subs --write-auto-subs --sub-langs en -o "data/youtube/%(id)s.%(ext)s" N45u5W3rOBc wvTrlW5z4SM
   ```

2. Extract and cache landmarks for the family video:

   ```bash
   .venv/bin/python validation/extract.py data/youtube/N45u5W3rOBc.mp4
   ```

3. Score whole signs on the family video:

   ```bash
   .venv/bin/python validation/validate_family.py
   ```

4. Score the fingerspelling-sequence model on the alphabet video:

   ```bash
   .venv/bin/python validation/validate_alphabet.py
   ```

5. Score our A–Z letter model on the alphabet video:

   ```bash
   .venv/bin/python validation/validate_letters.py
   ```

## Results (Apple M4, 2026-10-26/27)

### Whole signs: pretrained ISLR 1st-place model, `reports/family-islr.json`

**Teaching spans** (the signer demonstrates one sign several times):
- The span vote is correct for **6 of 7** in-vocabulary signs (dad, mom, grandpa, grandma, aunt, uncle). Brother loses to "all".
- Per segment, the right sign is top-1 in 40% of segments and top-5 in 60%. Many segments are explanation gestures, not the sign itself.

**Fast review sequence:** dad → mom → grandpa → grandma → brother comes out in order. Grandma and brother are right but at low confidence (0.10–0.15).

**Confidence:**
- Correct guesses have a median confidence of **0.72**; wrong ones and out-of-vocabulary signs about **0.20**.
- The default floor `ML_MIN_SIGN_CONFIDENCE=0.35` keeps 78% of correct guesses and drops about 77% of wrong ones.

**Through the full stack** (phone path: Go → Python → generator):
- A 4 s "dad" demo became `DAD` (0.85) plus a stray `MAN` (0.41).
- The review 2 clip became `AUNT` (0.95) and `UNCLE` (0.94) plus a stray `PLEASE` (0.42).
- Each took 2.5–4.4 s end to end.

### Letters A–Z, `reports/alphabet.json` and `reports/letters.json`

| Model | Letters right (span vote) | Notes |
| --- | --- | --- |
| Skunk0 fingerspelling CTC (Core ML, trained on Google's fingerspelling phrases) | 4 / 26 (15%) at best | Decodes mostly digits and symbols on held single letters with no body in view. **Not used.** |
| **Our A–Z hand-shape MLP** (21 hand points, trained on 8,599 photos) | **20 / 26 (77%)** | Misses look-alike shapes (C→D, N→M, R→S, U→R, V→W) and J, which is drawn in the air. |

**Through the full stack:** a B clip gave `B` (0.96), and a B-then-C clip was spelled **`BC`**.

### Generator: glosses → sentence, `benchmarks/reports/m4-islr-*.json`

The test is 16 gloss sequences built from the recognizer's own vocabulary (`benchmarks/islr_glosses.jsonl`). None of them appear in any training data.

| Generator | Exact | Passed the constraint | p50 |
| --- | --- | --- | --- |
| Qwen3.5-2B base | 56% | 94% | 1.02 s |
| Qwen3.5-2B + LoRA r2 (ours) | 50% | 75% | 1.16 s |
| **Qwen3.5-4B 4-bit, no fine-tune** | **69%** | **100%** | **0.86 s** |

**The 4B is now the default generator.** Our LoRA was tuned on pairs written in one author's style, and it over-fits: it gives "Hello is your mom." and "My dog is a dog." on the recognizer's real vocabulary.

## Caveats

- Each video has one signer, and the spans are from captions, not frame-exact labels. Treat these as sanity checks, not benchmark numbers.
- The letter photos (Marxulia/asl_sign_languages_alphabets_v03) have **no stated licence**. They were used only to train a local model. Check the licence before distributing that model.
