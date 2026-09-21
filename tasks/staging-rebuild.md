# Recreate staging box 195.35.14.177 (Ubuntu 24.04, SHARED with auto-author)

Old box (47.88.89.175) died. New box already has py3.12, node18, pm2, nginx, pg16,
redis7, certbot, ufw, ffmpeg. Missing: uv, podcastfy user, /opt tree, db, site.
Decisions (user): DNS already repointed (resolves ✓), EMPTY db fresh start, generate
fresh secrets (AWS/provider keys left blank).

Shared-box safety: do NOT run harden-host.sh verbatim (`ufw --force reset` wipes the
"Frank Cox subnet" rule; `pm2 unstartup` touches root's daemon). ufw already correct
(22/80/443). Do the safe subset manually.

## Steps
- [ ] 1. Generate: deploy keypair (ed25519), JWT_SECRET_KEY, ENCRYPTION_KEY, db superuser pw
- [ ] 2. Provision box (root): podcastfy user + authorized_keys(deploy pub), /opt tree+logs,
        uv (+/usr/local/bin symlink), pm2 startup for podcastfy
- [ ] 3. Postgres: CREATE ROLE podcastfy SUPERUSER LOGIN; CREATE DATABASE podcastfy
        (podcastfy_app + fixed password created by migration 003)
- [ ] 4. Write /opt/podcaststudiohub/api/.env (600, podcastfy); AWS/provider keys blank
- [ ] 5. GH env `development`: SERVER_HOST->195.35.14.177, SSH_PRIVATE_KEY=new deploy key,
        SERVER_USER=podcastfy, fix NEXTAUTH_URL typo (podcaststudio.me -> podcaststudiohub.me)
- [ ] 6. nginx+SSL: provision-ssl.sh DOMAIN=dev.podcaststudiohub.me, then fix ports 8001->8005/3003->3010
- [ ] 7. Trigger deploy-dev.yml (skip_tests=true bring-up: still rsyncs+migrates+pm2+healthcheck)
- [ ] 8. Verify: pm2 list, curl https health + frontend
- [ ] 9. Update memory (dev-vps IP)

## Flags
- NEXTAUTH_URL had typo (missing "hub"); fixing to match API_URL/FRONTEND_URL.
- AWS S3 + provider API keys blank in .env — user fills before generation works.
