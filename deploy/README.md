# Deploy: the backend on Keanu's VPS

`https://pillow.keanuc.net` is served by the VPS, not by a laptop. Two containers
(`compose.yml`): the backend, and `cloudflared` running the `calhacks-pillow` tunnel to it.

## How a change goes live

1. Open a PR. `.github/workflows/backend.yml` runs `ruff` and `pytest` on it.
2. Merge to master. The workflow's `deploy` job SSHes to the VPS and runs `deploy.sh <sha>`: check
   out the commit, rebuild, restart, wait for `/api/health`. If that fails it rolls back to the
   commit that was running, and the job goes red.
3. Redeploy master by hand: Actions tab > backend > Run workflow.

Nobody runs `cloudflared` for `calhacks-pillow` on a laptop any more: two runners split traffic.
Develop against your own `uvicorn` on localhost with your own `backend/.env`. The VPS runs the
Night Watch and reminder tickers against Supabase, so a second public backend would double them.

## The VPS side (already set up; for reference)

- User `deploy` (in the `docker` group). Repo clone: `/opt/pillow/repo`, fetched with a read-only
  GitHub deploy key.
- `/opt/pillow/backend.env`: the backend's settings (`backend/.env.example` names them).
  `/opt/pillow/tunnel.json`: the tunnel credentials. Both secrets, neither in git.
- `~deploy/.ssh/authorized_keys`: the CI key, restricted to
  `command="/opt/pillow/repo/deploy/deploy.sh",restrict`.
- GitHub repo secrets: `DEPLOY_HOST`, `DEPLOY_SSH_KEY` (the CI key's private half),
  `DEPLOY_KNOWN_HOSTS`.

Logs: `ssh <vps> 'docker compose -p pillow logs -f backend'`. Change a setting: edit
`backend.env`, then `docker compose -p pillow up -d backend` (as `deploy`, in `/opt/pillow/repo/deploy`).
