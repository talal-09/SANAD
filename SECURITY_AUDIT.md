# SANAD Security Audit

Last reviewed: September 20, 2026.

## Implemented Protections

- Search and application queries use parameterized Django ORM operations. The application does not use raw SQL, `RawSQL`, or `extra()`.
- Every POST form uses CSRF protection; no application view is exempted with `csrf_exempt`.
- Django templates escape user input by default, and the Content Security Policy restricts unauthorized scripts and resources.
- Post-login redirects accept local destinations only.
- Failed sign-in attempts are limited by default to five attempts per IP address and username within ten minutes.
- Public registration is disabled automatically when `DJANGO_DEBUG=0`; production accounts must be provisioned by an administrator.
- Patient, imaging, follow-up, and notification records are restricted to the healthcare organization associated with the authenticated user. Cross-organization identifiers return HTTP 404.
- DICOM studies and medical reports are stored outside the public media directory.
- ZIP uploads enforce file-size, entry-count, and compression-ratio limits and reject Zip Slip paths, symbolic links, and executable files.
- Report uploads must use a PDF extension and contain a valid PDF signature. Authorized downloads are served as private attachments.
- Authenticated pages use `private, no-store` cache controls.
- Clickjacking protection, MIME-sniffing protection, Permissions Policy, and Content Security Policy headers are enabled.

## Production Configuration

Set the following values in the server environment. Never commit their real values:

```text
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<random-secret-value-at-least-50-characters-long>
DJANGO_ALLOWED_HOSTS=sanad.example.sa
```

When development mode is disabled, SANAD enables HTTPS redirects, secure cookies, and HSTS automatically. Deploy behind a production WSGI or ASGI server with a valid HTTPS certificate. Configure the front-end server's request-body limit so it does not exceed the intended DICOM upload limit. Do not use `manage.py runserver` in production.

Run the following checks before deployment:

```powershell
python manage.py migrate
python manage.py test
python manage.py check --deploy
python -m pip check
```

## Operational Notes

- Login throttling currently uses Django's local cache. This is appropriate for the prototype and a single server process. Multi-process or multi-server deployments should use a shared cache such as Redis or rate limiting at the web gateway.
- Organization isolation depends on the healthcare organization of the employee who registered the patient. Legacy records without `registered_by` remain hidden from staff until an administrator assigns the correct owner.
- The project pins supported Django `6.1.1` and `pydicom 3.0.2`, which includes a DICOMDIR security fix. Review security updates before every deployment.
- This review covers application code, configuration, and internal tests. It is not an external penetration test of cloud or network infrastructure.
