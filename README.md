# SANAD

[![Tests](https://github.com/talal-09/SANAD/actions/workflows/tests.yml/badge.svg)](https://github.com/talal-09/SANAD/actions/workflows/tests.yml)

**Documentation language: English**

**[Explore the live SANAD showcase](https://talal-09.github.io/SANAD/)**

The showcase supports Arabic and English through the language switch in the main navigation.

SANAD is an Arabic-first research prototype that helps radiologists review potential pulmonary nodules in CT scans, correct their location and measurements, and move each case through a clear follow-up workflow.

> SANAD is an educational and research project. It is not a medical device and must not be used for diagnosis or independent treatment decisions. The final decision always belongs to a qualified clinician.

## Project Preview

<p align="center">
  <img src="docs/assets/sanad-english.png" alt="Screenshot of the English SANAD showcase with the language switch and CT review interface" width="100%">
</p>

<p align="center">
  <img src="docs/assets/sanad-interactive-demo.png" alt="English SANAD interactive workflow demo showing the patient review step" width="100%">
</p>

> These interface previews use synthetic demonstration data only.

## What SANAD Does

1. Registers a patient and links the case to a healthcare organization.
2. Accepts a protected CT study upload.
3. Runs a MONAI model to identify potential findings.
4. Lets a radiologist accept, correct, or reject each candidate.
5. Creates follow-up plans and notifications automatically.

## Technology Stack

- Django 6.1
- MONAI and PyTorch
- pydicom for DICOM processing
- SQLite for local development
- Responsive bilingual Arabic-English user interface
- Optional private Cloudinary storage

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Cloudinary Integration

SANAD stores DICOM files and generated PDF reports locally by default. To enable Cloudinary, copy the **API Environment variable** from the Cloudinary dashboard into the local `.env` file:

```dotenv
CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name?secure=true
SANAD_CLOUDINARY_ENABLED=1
SANAD_CLOUDINARY_FOLDER=sanad/private-medical
```

Restart the server after changing the environment. New files are uploaded as `raw/authenticated` assets and the application does not expose a public delivery URL for them. A protected temporary copy is downloaded to `private_uploads/cloudinary_cache` only when DICOM analysis requires a local filesystem path. Existing local uploads are not migrated automatically.

Validate the connection without uploading a file:

```powershell
python manage.py check_cloudinary
```

> Medical imaging data is sensitive health information. Do not use a production Cloudinary account for real patient data until you have verified data-residency requirements, a suitable data-processing agreement, applicable regulatory obligations, and any required BAA for your use case.

## AI Environment

The AI environment is kept separate because of the size and hardware-specific requirements of PyTorch and MONAI. Install the PyTorch build appropriate for your GPU, then run:

```powershell
python -m venv .venv-ai
.\.venv-ai\Scripts\Activate.ps1
python -m pip install -r requirements-ai.txt
```

Model weights are not stored in Git. Place the approved model at:

```text
ai_models/lung_nodule_ct_detection/models/model.pt
```

Override the default paths with `SANAD_AI_PYTHON` and `SANAD_AI_MODEL_ROOT` when needed.

## Tests

```powershell
python manage.py test
python manage.py check --deploy
```

The current suite contains 74 automated tests covering authorization, organization-level data isolation, uploads, private cloud storage, model-result review, notifications, and error handling.

## Model Results

See [MODEL_CARD.md](MODEL_CARD.md) for detailed results and limitations. On the held-out LUNA16 test set, the model detected 97 of 102 nodules with 2.51 false positives per scan. This is a research result, not clinical validation.

## Privacy and Security

- The repository contains no patient records, DICOM studies, or local database files.
- Medical files are stored outside the public media directory and are protected by organization-level authorization.
- The application includes CSRF and CSP protections, ZIP upload limits, and login-attempt controls.
- See the [Security Policy](SECURITY.md), [Security Audit](SECURITY_AUDIT.md), and [Usage Policy](USAGE_POLICY.md).

## Data and Attribution

The detection model uses MONAI and the LUNA16 dataset derived from LIDC-IDRI. Dataset terms and attribution requirements still apply. Licensing and reference details are documented in `ai_models/lung_nodule_ct_detection/docs`.

## License

SANAD is available under the [Apache License 2.0](LICENSE). External components and training data retain their own licenses and terms.
