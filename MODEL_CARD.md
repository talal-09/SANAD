# SANAD Model Card

## Intended Purpose

SANAD is a research prototype for identifying potential pulmonary nodule locations in three-dimensional CT scans. It presents model output to a radiologist for review, correction, or rejection. The model does not issue a final diagnosis.

## Data

- Base MONAI bundle: `lung_nodule_ct_detection`.
- Development and evaluation data: LUNA16, derived from LIDC-IDRI.
- This repository does not contain patient scans or LUNA16 data.

## Held-Out Test Result

The decision threshold selected on validation data was evaluated on 84 independent scans containing 102 consensus nodules:

| Metric | Result |
|---|---:|
| Detected nodules | 97 of 102 |
| Sensitivity | 95.1% |
| Positive predictive value (precision) | 31.5% |
| Missed nodules | 5 |
| False positives | 211 |
| False positives per scan | 2.51 |

## Limitations

- These results demonstrate that the training and evaluation pipeline operates end to end; they do not establish clinical validity.
- The model requires external, multi-center validation across different scanners, populations, and imaging protocols.
- The false-positive rate is substantial, so qualified clinician review remains mandatory.
- Model output must not be used as the sole basis for diagnosis, treatment, triage, or other clinical decisions.

## Model Weights

Model weights are not stored in Git. Publish only an approved model as a GitHub Release asset or in a controlled model registry, then document its download URL and SHA-256 checksum here.
