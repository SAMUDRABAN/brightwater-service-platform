# Release source provenance

The GitHub repository begins with a clean `0.2.0` release snapshot. Earlier local development checkpoint hashes referenced by historical investigation reports are not GitHub revisions. Their source and private evidence were retained separately; they are not silently represented as published commits.

The GitHub commit, CI checks and annotated `v0.2.0` tag identify the published release. Deployed components report their actual source commit. The office/API release can change independently of the India voice gateway, worker and scheduler; a new web version is not evidence that every service was rebuilt.

The release source excludes private environment files, credentials, caller recordings and database exports. Generated auditions are labelled and remain distinct from actual caller audio. Local browser-review data is isolated and not imported to production.
