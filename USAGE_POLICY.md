# SANAD Usage Policy

Last updated: September 27, 2026.

## Scope

SANAD is an educational and research prototype for demonstrating an AI-assisted pulmonary nodule review workflow. It is not a medical device and has not been validated or approved for clinical diagnosis or treatment.

## Permitted Use

- Research, education, software evaluation, and demonstrations using synthetic, de-identified, or properly authorized data.
- Local development and security testing performed within systems and data that the tester is authorized to access.
- Review of model output by qualified professionals as part of a controlled research study with appropriate oversight.

## Prohibited Use

- Using SANAD or its model output as the sole basis for diagnosis, treatment, triage, or any other clinical decision.
- Uploading identifiable patient data without a lawful basis, required approvals, suitable contracts, and appropriate technical safeguards.
- Publishing credentials, API keys, DICOM studies, patient records, local databases, or other sensitive information in issues, commits, logs, or screenshots.
- Attempting to access another organization’s data or bypass authentication, authorization, upload validation, or audit controls.
- Representing research metrics as clinical validation, regulatory approval, or guaranteed performance.

## User Responsibilities

Users are responsible for complying with applicable privacy, medical-device, cybersecurity, data-residency, research-ethics, and intellectual-property requirements. Before processing health information, verify the deployment architecture, access controls, retention rules, incident-response process, and contracts with every service provider.

## Model and Data Limitations

The model can miss nodules and produce false positives. Performance may vary across populations, scanners, imaging protocols, and deployment environments. Dataset licenses and attribution requirements remain applicable. See [MODEL_CARD.md](MODEL_CARD.md) for measured results and limitations.

## Security and Reporting

Follow [SECURITY.md](SECURITY.md) when reporting vulnerabilities. Do not include sensitive information in public reports.

## Disclaimer

The software is provided under the [Apache License 2.0](LICENSE), without warranties or conditions beyond those stated in that license. This usage policy provides project guidance and does not replace professional legal, regulatory, privacy, or clinical advice.
