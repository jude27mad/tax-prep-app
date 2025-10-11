# CRA EFILE Suitability Checklist

**2025 filing window**: CRA EFILE opens Feb 24, 2025 and closes Jan 30, 2026. Ensure all 2024 backfile transmissions are submitted before the cutoff.

**T183 retention**: Maintain each signed T183 (masking first five SIN digits) and accompanying e-sign audit trail for six years after the signature date.

1. **Gather credentials**
   - Business number and firm legal name
   - Preparer contact, phone, secure email
   - Signed RC59 (if representing clients) and T183 template

2. **Submit suitability application**
   - Log in to CRA EFILE portal (<https://www.canada.ca/efile>)
   - Complete the annual "Application for EFILE" questionnaire
   - Upload supporting documents if CRA requests proof of identity or compliance

3. **Monitor CRA correspondence**
   - CRA may take 2-6 weeks to approve/renew suitability
   - Respond to follow-up questions immediately (they usually arrive by secure mail)

4. **Register software**
   - Once approved, register this application as the certified software you intend to use
   - CRA releases pre-season certification test cases mid-November; schedule time to run them

5. **Maintain compliance**
   - Keep T183 e-sign logs for 6 years (per CRA retention rule)
   - Renew suitability annually before filing season opens
   - Track any CRA bulletins for rule changes, especially RC4018 updates

## Migration

### Python multipart parser requirement

FastAPI's HTML form endpoints (used by the preparer UI) now depend on the
[`python-multipart`](https://pypi.org/project/python-multipart/) package. Deploy
targets created before this change should be updated to install the new
dependency when refreshing virtual environments or container images.

1. **Install the package** – run `pip install python-multipart` (or refresh from
   `requirements.txt`) in every runtime that serves the UI routes.
2. **Validate availability** – execute `python -c "import python_multipart; print(python_multipart.__version__)"`
   or `pip show python-multipart` after deployment. Either command confirms the
   interpreter can import the parser.
3. **CI / build pipelines** – add the same validation step to Dockerfiles or CI
   jobs so missing dependencies fail fast before going live.

Without the package, POST requests that submit forms through `/ui/...` will
return `500 Internal Server Error` responses because Starlette cannot parse the
incoming multipart payload.
