# Deploying the QZ signing certificate across sites (demo → live)

Each site signs QZ Tray requests with a cert pair in its own site folder:

    sites/<site>/qz-certificate.pem     (public — handed to browsers / becomes override.crt)
    sites/<site>/qz-private-key.pem     (private — never leaves the server)

A Windows machine's `override.crt` trusts EXACTLY ONE certificate. So if demo
and live have different certs, a machine set up for demo will re-prompt on live.

## Recommendation: one shared pair for every site

Generate ONE pair, drop it into every site folder. Then a single
`setup-print-machine.bat` (or one Allow+Remember) trusts demo, live and local
alike. The only thing that differs between demo and live is the DOMAIN you
download the installer from — the embedded cert is identical.

### Step 1 — pick the master pair (once, ever)

Reuse the pair the office machines already trust — the local `avinas` pair —
so their existing override.crt keeps working:

    MASTER_CERT=sites/avinas/qz-certificate.pem
    MASTER_KEY=sites/avinas/qz-private-key.pem

(or generate a brand-new one — see qz_security.py header — if starting clean.)

### Step 2 — install it into a target site (run ON that server)

From the bench root:

    SITE=<demo-or-live-site>
    cp <MASTER_CERT> sites/$SITE/qz-certificate.pem
    cp <MASTER_KEY>  sites/$SITE/qz-private-key.pem
    chmod 600 sites/$SITE/qz-private-key.pem

Nothing else — the sign/certificate endpoints read the files per request, no
restart needed. Verify:

    bench --site $SITE execute avinashgroup_app.custom_code.printing.qz_security.certificate | head -c 60

## Testing flow

- DEMO: browse the demo domain, download setup-print-machine.bat from
  /api/method/avinashgroup_app.custom_code.printing.qz_security.setup_print_machine_bat,
  double-click on the print machine. Test printing.
- LIVE: same machine, browse the LIVE domain, print. If demo & live share the
  master pair, NO re-setup — it just works. (If you skipped the shared-pair
  step, re-download+run the installer from the live domain.)

## If you must keep separate certs per site

Then run setup-print-machine.bat once per domain on each machine. The last one
run wins for override.crt (silent), but QZ's allowed.dat keeps every
Allow+Remember you have ever accepted, so older sites still print — just with
the fingerprint stored rather than the override. Shared pair is simpler.
